"""
HELXAIC Lyrics Engine
Core data structures, LRC format parser, embedded metadata tag extractor,
robust LRCLIB API client with candidate splitting & search cascades,
persistent disk caching, and asynchronous Qt worker.

Component Name: LyricsEngine
"""

import os
import re
import json
import bisect
import time
import urllib.request
import urllib.parse
import ssl
import hashlib
import html
import threading
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple, Callable
from PySide6.QtCore import QThread, Signal


@dataclass
class LyricLine:
    """Represents a single timestamped or plain lyric entry."""
    time_ms: int              # Milliseconds from start of track (-1 for unsynced)
    text: str                 # Lyric text content
    translation: Optional[str] = None  # Active displayed subtitle line
    romaji: Optional[str] = None       # General Latin Romaji pronunciation stream
    google_romaji: Optional[str] = None     # Dedicated Google Translate AI Romanized line
    genius_romaji: Optional[str] = None     # Dedicated Genius.com Romanized line
    netease_romaji: Optional[str] = None    # Dedicated NetEase timed Romaji line
    raw_translation: Optional[str] = None  # Native translation stream


@dataclass
class LyricData:
    """Complete lyric dataset for a track."""
    is_synced: bool           # True if timestamps exist, False for plain text
    lines: List[LyricLine]    # Ordered list of cues sorted by time_ms
    source: str               # 'Local .LRC', 'Embedded Tag', 'Cached (LRCLIB)', 'LRCLIB Online', 'none'
    title: str                # Track title
    artist: str               # Track artist
    album: str = ""           # Album name
    offset_ms: int = 0        # User sync offset in ms
    plain_text: str = ""      # Full raw text fallback
    has_romaji: bool = False
    has_google_romaji: bool = False
    has_genius_romaji: bool = False
    has_netease_romaji: bool = False
    has_translation: bool = False
    genius_url: str = ""
    romaji_status: str = "none"         # 'available' | 'rate_limited' | 'failed' | 'none'
    romaji_attempt_ts: float = 0.0      # Timestamp of last enrichment attempt


class LRCParser:
    """High-speed regular expression based LRC format parser."""
    # Matches standard [mm:ss.xx], [mm:ss.xxx], [mm:ss:xx], [mm:ss], and NetEase [mm:ss.xx-1] or [mm:ss.xxx-1]
    TIMESTAMP_REGEX = re.compile(r'\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?(?:-\d+)?\]')
    TAG_REGEX = re.compile(r'\[([a-zA-Z]+):(.*?)\]')

    @classmethod
    def parse(cls, raw_text: str, title: str = "", artist: str = "") -> LyricData:
        lines_output: List[LyricLine] = []
        offset_ms = 0
        tag_title = title
        tag_artist = artist

        for raw_line in raw_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            # Check for header metadata tags like [offset:+500], [ti:Song], [ar:Artist]
            tag_match = cls.TAG_REGEX.match(line)
            if tag_match and not cls.TIMESTAMP_REGEX.match(line):
                tag_name = tag_match.group(1).lower()
                tag_val = tag_match.group(2).strip()
                if tag_name == 'offset':
                    try:
                        offset_ms = int(tag_val)
                    except ValueError:
                        pass
                elif tag_name == 'ti' and tag_val:
                    tag_title = tag_val
                elif tag_name == 'ar' and tag_val:
                    tag_artist = tag_val
                continue

            # Extract all timestamps on this line (supports multiple timestamps like [00:12.34][00:45.67]Chorus)
            timestamps = cls.TIMESTAMP_REGEX.findall(line)
            if timestamps:
                # Remove timestamps to get clean lyric text
                clean_text = cls.TIMESTAMP_REGEX.sub('', line).strip()
                for mm, ss, ms_part in timestamps:
                    try:
                        mins = int(mm)
                        secs = int(ss)
                        if ms_part:
                            if len(ms_part) == 1:
                                ms = int(ms_part) * 100
                            elif len(ms_part) == 2:
                                ms = int(ms_part) * 10
                            else:
                                ms = int(ms_part[:3])
                        else:
                            ms = 0
                        total_ms = (mins * 60 + secs) * 1000 + ms + offset_ms
                        lines_output.append(LyricLine(time_ms=max(0, total_ms), text=clean_text))
                    except Exception:
                        continue

        lines_output.sort(key=lambda x: x.time_ms)
        is_synced = len(lines_output) > 0

        # Fallback if no timestamps were found (plain text lyrics)
        if not is_synced:
            lines_output = []
            for raw_l in raw_text.splitlines():
                l = raw_l.strip()
                if not l or cls.TAG_REGEX.match(l):
                    continue
                # Clean any stray timestamp brackets (e.g. [00:00.00-1]) from plain text display
                clean_plain = cls.TIMESTAMP_REGEX.sub('', l).strip()
                if clean_plain:
                    lines_output.append(LyricLine(time_ms=-1, text=clean_plain))

        return LyricData(
            is_synced=is_synced,
            lines=lines_output,
            source='LRC',
            title=tag_title,
            artist=tag_artist,
            offset_ms=offset_ms,
            plain_text=raw_text
        )


def is_valid_lyric_content(data: Optional[LyricData]) -> bool:
    """
    Determines if LyricData contains genuine lyrical content,
    as opposed to only metadata, copyright, composer credits, or instrumental notices.
    """
    if not data or not data.lines:
        return False
    
    valid_lines = [l for l in data.lines if l.text and l.text.strip()]
    if not valid_lines:
        return False
    
    # Common credit, metadata, and instrumental notice patterns
    NON_LYRIC_PATTERNS = re.compile(
        r'^(作词|作曲|编曲|制作人|监制|录音|混音|母带|吉他|贝斯|鼓|键盘|和声|弦乐|词[：:]|曲[：:]|'
        r'written by|composed by|produced by|arranged by|mixed by|mastered by|lyrics by|'
        r'lyricist|composer|producer|credits|record label|published by|'
        r'纯音乐|请欣赏|instrumental|no lyrics available|music only)\b',
        re.IGNORECASE
    )
    
    actual_lyric_lines = 0
    for l in valid_lines:
        clean = l.text.strip()
        if NON_LYRIC_PATTERNS.search(clean):
            continue
        # Check if line has meaningful lyrical text (at least 2 letters/characters)
        if len(re.sub(r'[\W_]+', '', clean)) >= 2:
            actual_lyric_lines += 1
            
    if actual_lyric_lines == 0:
        return False
        
    return True


class LyricQuerySanitizer:
    """
    Advanced sanitization engine for YouTube video titles, audio filenames,
    and metadata strings. Removes video fluff, CJK brackets, leading track numbers,
    anime OP/ED descriptors, and accurately separates/deduplicates (artist, title) pairs.
    """
    GENERIC_ARTISTS = {
        'single track', 'unknown', 'unknown artist', 'various', 'various artists',
        'n/a', 'none', '-', '--', 'undefined', 'audio', 'track', 'song', 'artist',
        'youtube', 'auto-generated by youtube', 'null', 'アニメ', 'anime', 'tvアニメ',
        'テレビアニメ', 'ノンクレジット'
    }

    RE_EXTENSIONS = re.compile(
        r'\.(mp4|mp3|mkv|webm|flac|wav|m4a|opus|ogg|aac|wma|mov|avi|m4v)$',
        re.IGNORECASE
    )
    RE_TRACK_NUMBERS = re.compile(r'^\s*\d{1,3}\s*[-._)\s]\s*')
    
    # Anime metadata in parentheses or brackets (e.g. (TVアニメ「...」OPテーマ), （テレビアニメ「鬼滅の刃」...）)
    RE_ANIME_PARENS = re.compile(
        r'[\(\[（【][^\(\)\[\]（）【】]*?(?:TV\s*アニメ|テレビアニメ|アニメ|anime|OPテーマ|EDテーマ|オープニング|エンディング|主題歌|theme\s*song|soundtrack|insert\s*song)[^\(\)\[\]（）【】]*?[\)\]）】]',
        re.IGNORECASE
    )

    # Anime prefix descriptors at the start of a string: e.g. "アニメ『Dr.STONE』", "TVアニメ「呪術廻戦」"
    RE_ANIME_PREFIX = re.compile(
        r'^(?:\s*(?:TV\s*)?(?:テレビ)?(?:アニメ|anime)\s*[『「].*?[』」]\s*)+',
        re.IGNORECASE
    )

    # Anime fluff words (season, cour, non-credit, op/ed)
    RE_ANIME_FLUFF_WORDS = re.compile(
        r'(?i)\b(?:第\d{1,2}[期クール]|シーズン\s*\d{1,2}|Season\s*\d{1,2}|最終シーズン|遊郭編|渋谷事変|死滅回游|刀鍛冶の里編|柱稽古編|無限列車編|'
        r'ノンクレジット\s*(?:OP|ED|オープニング|エンディング|テーマ|曲|映像|ムービー|次回予告)*|'
        r'non[-\s]?credit(?:ed)?\s*(?:OP|ED|opening|ending|theme|movie|video)*|'
        r'(?:OP|ED|オープニング|エンディング)(?:テーマ|曲|映像|ムービー|テーマソング|次回予告)?|'
        r'opening\s*theme|ending\s*theme|main\s*theme|theme\s*song|insert\s*song|bgm|ost|soundtrack)\b',
        re.IGNORECASE
    )

    # CJK brackets: 【...】, ［...］, 《...》, 〈...〉
    RE_CJK_TAGS = re.compile(r'【.*?】|［.*?］|《.*?》|〈.*?〉')

    # Common video/audio suffixes in parentheses or brackets
    RE_NOISE_PARENS = re.compile(
        r'[\(\[（【][^\(\)\[\]（）【】]*?(?:official|music|video|audio|visualizer|lyric|lyrics|mv|pv|hd|4k|'
        r'remaster|live|acoustic|cover|full\s*song|original|clean|explicit|version|'
        r'\d{2,3}k|kara|karaoke|off\s*vocal|on\s*vocal|instrumental|歌ってみた|covered|'
        r'indo\s*sub|color\s*coded|rom/han/eng|terjemahan|lirik|'
        r'dir(?:\.|ected)?\s+by|prod\.\s*by|ft\.|feat\.)[^\(\)\[\]（）【】]*?[\)\]）】]',
        re.IGNORECASE
    )

    RE_OFFICIAL_SUFFIX = re.compile(
        r'(?i)\b(official\s+music\s+video|official\s+video|official\s+audio|official\s+mv|'
        r'official\s+lyric\s+video|lyrics\s+video|music\s+video|official\s+track|official\s+visualizer|hd|4k|remastered)\b'
    )

    # Descriptive OST / battle theme / soundtrack suffixes after hyphen or colon
    RE_OST_SUFFIX = re.compile(
        r'(?i)\s*[-—–:~]\s*.*?\b(?:battle\s*theme|main\s*theme|theme\s*song|theme|ost|soundtrack|insert\s*song|bgm)\b.*$'
    )

    # Trailing YouTube suffixes
    RE_YOUTUBE_SUFFIX = re.compile(
        r'(?i)\s*[-—–:~|／/]?\s*YouTube\s*$'
    )

    # Uploader / Channel noise
    RE_ARTIST_NOISE = re.compile(
        r'(?i)\b(topic|vevo|official|channel|records|entertainment|music)\b'
    )

    @classmethod
    def clean_title(cls, title: str) -> str:
        if not title:
            return ""
        t = str(title).strip()
        t = cls.RE_EXTENSIONS.sub('', t)
        t = cls.RE_TRACK_NUMBERS.sub('', t)
        t = cls.RE_CJK_TAGS.sub(' ', t)
        t = cls.RE_ANIME_PARENS.sub(' ', t)
        t = cls.RE_NOISE_PARENS.sub(' ', t)
        t = cls.RE_OFFICIAL_SUFFIX.sub(' ', t)
        t = cls.RE_OST_SUFFIX.sub('', t)
        t = cls.RE_YOUTUBE_SUFFIX.sub('', t)
        t = re.sub(r'[_]+', ' ', t)
        t = re.sub(r'\s{2,}', ' ', t)
        return t.strip(' -._:~|／/｜()[]（）')

    @classmethod
    def clean_artist(cls, artist: str) -> str:
        if not artist:
            return ""
        a = str(artist).strip()
        if a.lower() in cls.GENERIC_ARTISTS:
            return ""
        a = cls.RE_EXTENSIONS.sub('', a)
        a = cls.RE_ANIME_PARENS.sub(' ', a)
        a = re.sub(r'\[.*?\]|\(.*?\)|【.*?】|［.*?］|『.*?』|「.*?」|（.*?）', ' ', a)
        a = cls.RE_ANIME_PREFIX.sub(' ', a)
        a = cls.RE_ANIME_FLUFF_WORDS.sub(' ', a)
        a = re.sub(r'\s*-\s*topic\b', '', a, flags=re.IGNORECASE)
        a = cls.RE_ARTIST_NOISE.sub(' ', a)
        a = re.sub(r'[_]+', ' ', a)
        
        # If artist string contains delimiters (e.g. "Fluff - ALI"), pick the cleanest rightmost segment
        for sep in [' - ', ' -- ', ' — ', ' – ', '／', ' / ', '｜', ' | ', ' : ', '：']:
            if sep in a:
                parts = a.split(sep)
                for p in reversed(parts):
                    p_c = p.strip(' -._:~|／/｜()[]（）')
                    p_clean = cls.RE_ANIME_FLUFF_WORDS.sub('', p_c).strip()
                    if p_clean and p_clean.lower() not in cls.GENERIC_ARTISTS and len(p_clean) >= 2:
                        a = p_clean
                        break
                break

        a = re.sub(r'\s{2,}', ' ', a)
        a = a.strip(' -._:~|／/｜()[]（）')
        return "" if a.lower() in cls.GENERIC_ARTISTS else a

    @classmethod
    def extract_candidates(cls, raw_title: str, raw_artist: str = "") -> List[Tuple[str, str]]:
        """
        Extract prioritized list of (title, artist) candidate pairs.
        Handles YouTube formats, separators, Japanese quotes, anime OP/ED descriptors,
        'by' syntax, and artist deduplication.
        """
        results: List[Tuple[str, str]] = []
        seen = set()

        def add_cand(t: str, a: str):
            clean_t = cls.clean_title(t)
            clean_a = cls.clean_artist(a)
            if not clean_t:
                return
            key = (clean_t.lower(), clean_a.lower())
            if key not in seen:
                seen.add(key)
                results.append((clean_t, clean_a))

        c_title = cls.clean_title(raw_title)
        c_artist = cls.clean_artist(raw_artist)

        # 1. Strip anime / noise parentheticals before quote analysis
        prep_title = cls.RE_ANIME_PARENS.sub(' ', str(raw_title))
        prep_title = cls.RE_NOISE_PARENS.sub(' ', prep_title)

        # 2. Check Japanese Quotes [Artist] 「Title」 or [Artist] 『Title』
        matches = list(re.finditer(r'([^\s／/|—–:~「『【\[\]]+(?:\s+[^\s／/|—–:~「『【\[\]]+)*)?\s*[「『]([^「『」』]+)[」』]', prep_title))
        if matches:
            for m in reversed(matches):
                prefix_art = m.group(1) or ""
                quote_text = m.group(2).strip()
                clean_art = cls.clean_artist(prefix_art)
                if clean_art:
                    add_cand(quote_text, clean_art)
                    add_cand(quote_text, c_artist or clean_art)
                else:
                    add_cand(quote_text, c_artist)

        # 3. Check "Title by Artist"
        m_by = re.search(r'^(.*?)\s+by\s+(.*?)$', c_title, flags=re.IGNORECASE)
        if m_by:
            by_t, by_a = m_by.group(1).strip(), m_by.group(2).strip()
            add_cand(by_t, by_a or c_artist)

        # 4. Check Standard Separators: ' - ', ' -- ', ' — ', ' – ', '／', ' / ', '｜', ' | ', ' : ', '：'
        stripped_anime = cls.RE_ANIME_PREFIX.sub('', prep_title).strip()
        stripped_anime = cls.RE_ANIME_FLUFF_WORDS.sub('', stripped_anime).strip(' -._:~／/｜:【】()[]')
        
        separators = [' - ', ' -- ', ' — ', ' – ', '／', ' / ', '｜', ' | ', ' : ', '：', ' -', '- ']
        for text_to_split in [stripped_anime, c_title]:
            for sep in separators:
                if sep in text_to_split:
                    parts = text_to_split.split(sep, 1)
                    left = parts[0].strip(' -._「」『』()[]【】（）')
                    right = parts[1].strip(' -._「」『』()[]【】（）')
                    
                    # Check if right or left has quotes: e.g. right = 'ALI 「CASANOVA POSSE」'
                    m_r = re.search(r'^(.*?)\s*[「『](.*?)[」』]', right)
                    if m_r:
                        sub_a, sub_t = m_r.group(1).strip(), m_r.group(2).strip()
                        if sub_t:
                            add_cand(sub_t, cls.clean_artist(sub_a) or c_artist)
                    
                    m_l = re.search(r'^(.*?)\s*[「『](.*?)[」』]', left)
                    if m_l:
                        sub_a, sub_t = m_l.group(1).strip(), m_l.group(2).strip()
                        if sub_t:
                            add_cand(sub_t, cls.clean_artist(sub_a) or c_artist)

                    clean_l = cls.clean_artist(left)
                    clean_r = cls.clean_title(right)

                    if left and right:
                        if c_artist and c_artist.lower() in left.lower():
                            add_cand(right, c_artist)
                            add_cand(right, clean_l or left)
                        elif c_artist and c_artist.lower() in right.lower():
                            add_cand(left, c_artist)
                            add_cand(left, cls.clean_artist(right) or right)
                        else:
                            add_cand(right, clean_l or left)
                            add_cand(left, cls.clean_artist(right) or right)
                    break

        # 5. If c_artist is provided and c_title starts with c_artist
        if c_artist and c_title:
            if c_title.lower().startswith(c_artist.lower()):
                stripped_t = c_title[len(c_artist):].strip(' -._:~|／/｜')
                if stripped_t:
                    add_cand(stripped_t, c_artist)

        # 6. Base direct pair
        if c_title:
            add_cand(c_title, c_artist)

        # 7. Aggressive base title (stripping any residual parentheticals)
        base_t = re.sub(r'\(.*?\)|\[.*?\]|（.*?）|【.*?】|「.*?」|『.*?』', '', c_title).strip(' -._')
        if base_t and base_t != c_title:
            add_cand(base_t, c_artist)

        return results


class LyricMatchVerifier:
    """
    Precision semantic matching & relevance scoring engine for lyric candidates.
    Protects against returning lyrics from completely wrong tracks or artists.
    """
    NOISE_TOKENS = {
        'official', 'audio', 'video', 'music', 'mv', 'pv', 'hd', '4k', 'lyrics',
        'lyric', 'full', 'song', 'version', 'edit', 'the', 'a', 'an', 'by', 'feat',
        'ft', 'remaster', 'remastered', 'original', 'mix', 'instrumental', 'karaoke'
    }

    @classmethod
    def _tokenize(cls, text: str) -> set:
        if not text:
            return set()
        # Keep alphanumeric and CJK characters
        t = re.sub(r'[^\w\s\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]', ' ', text.lower())
        tokens = set(t.split())
        return tokens - cls.NOISE_TOKENS

    @classmethod
    def _levenshtein_ratio(cls, s1: str, s2: str) -> float:
        if not s1 or not s2:
            return 0.0
        if s1 == s2:
            return 1.0
        len1, len2 = len(s1), len(s2)
        if len1 == 0 or len2 == 0:
            return 0.0
        # Fast bounded DP table
        dp = [list(range(len2 + 1))] + [[i] + [0] * len2 for i in range(1, len1 + 1)]
        for i in range(1, len1 + 1):
            for j in range(1, len2 + 1):
                cost = 0 if s1[i - 1] == s2[j - 1] else 1
                dp[i][j] = min(
                    dp[i - 1][j] + 1,
                    dp[i][j - 1] + 1,
                    dp[i - 1][j - 1] + cost
                )
        dist = dp[len1][len2]
        return max(0.0, 1.0 - dist / max(len1, len2))

    @classmethod
    def calculate_title_similarity(cls, candidate_title: str, target_title: str) -> float:
        """
        Calculates multi-metric semantic similarity between candidate and target title.
        Combines Token Jaccard, Scaled Substring Containment, and Levenshtein distance.
        """
        if not candidate_title or not target_title:
            return 0.0

        clean_cand = LyricQuerySanitizer.clean_title(candidate_title).lower()
        clean_target = LyricQuerySanitizer.clean_title(target_title).lower()

        if not clean_cand or not clean_target:
            return 0.0

        if clean_cand == clean_target:
            return 1.0

        # Substring containment scaled by character length ratio
        containment = 0.0
        if len(clean_target) >= 3 and clean_target in clean_cand:
            ratio = len(clean_target) / float(len(clean_cand))
            containment = 0.90 * ratio
        elif len(clean_cand) >= 3 and clean_cand in clean_target:
            ratio = len(clean_cand) / float(len(clean_target))
            containment = 0.85 * ratio

        # Token Jaccard
        cand_tokens = cls._tokenize(clean_cand)
        target_tokens = cls._tokenize(clean_target)

        jaccard = 0.0
        if cand_tokens and target_tokens:
            overlap = cand_tokens.intersection(target_tokens)
            jaccard = len(overlap) / float(len(target_tokens | cand_tokens))
        elif not cand_tokens and not target_tokens:
            jaccard = 0.5

        # Levenshtein ratio
        lev = cls._levenshtein_ratio(clean_cand, clean_target)

        return max(containment, jaccard, lev)

    @classmethod
    def calculate_artist_similarity(cls, candidate_artist: str, target_artist: str) -> float:
        if not candidate_artist or not target_artist:
            return 0.0
        c_a = LyricQuerySanitizer.clean_artist(candidate_artist).lower()
        t_a = LyricQuerySanitizer.clean_artist(target_artist).lower()
        if not c_a or not t_a:
            return 0.0
        if c_a == t_a or t_a in c_a or c_a in t_a:
            return 1.0
        
        cand_tokens = cls._tokenize(c_a)
        target_tokens = cls._tokenize(t_a)
        if cand_tokens and target_tokens:
            overlap = cand_tokens.intersection(target_tokens)
            if overlap:
                return len(overlap) / float(len(target_tokens | cand_tokens))
        return cls._levenshtein_ratio(c_a, t_a)

    @classmethod
    def score_candidate(
        cls,
        candidate_title: str,
        candidate_artist: str,
        candidate_duration_s: float,
        target_title: str,
        target_artist: str = "",
        target_duration_s: float = 0.0,
        has_synced: bool = False
    ) -> Tuple[float, bool]:
        """
        Scores a candidate result and returns (score, is_qualified).
        Threshold for qualification: title similarity >= 0.45 and total score >= 40.
        """
        title_sim = cls.calculate_title_similarity(candidate_title, target_title)
        
        # Hard rejection: if title similarity is too low (< 0.45), reject immediately
        if title_sim < 0.45:
            return 0.0, False

        score = 0.0

        # 1. Title Similarity Contribution (0 - 50 pts)
        score += title_sim * 50.0

        # 2. Artist Correlation Contribution (-20 to +25 pts)
        if target_artist:
            clean_cand_art = LyricQuerySanitizer.clean_artist(candidate_artist)
            if clean_cand_art:
                artist_sim = cls.calculate_artist_similarity(candidate_artist, target_artist)
                if artist_sim >= 0.70:
                    score += 25.0
                elif artist_sim >= 0.40:
                    score += 10.0
                else:
                    score -= 20.0  # Mismatched artist penalty
            else:
                score += 0.0  # Unknown / generic candidate artist
        else:
            score += 5.0  # Neutral artist

        # 3. Synced Lyrics Bonus (15 pts)
        if has_synced:
            score += 15.0

        # 4. Duration Match Contribution (-45 to +15 pts)
        if target_duration_s > 0 and candidate_duration_s > 0:
            diff = abs(candidate_duration_s - target_duration_s)
            if diff <= 4.0:
                score += 15.0
            elif diff <= 10.0:
                score += 8.0
            elif diff > 30.0:
                score -= 25.0
            elif diff > 60.0:
                score -= 45.0
                if title_sim < 0.90:
                    return 0.0, False  # Reject completely if duration is wildly off and title is not exact

        is_qualified = (title_sim >= 0.45) and (score >= 40.0)
        return score, is_qualified


class LyricsCacheManager:
    """Manages persistent disk caching in %APPDATA%/HELXAID/lyrics_cache/ with thread-safe atomic file operations."""

    def __init__(self):
        self._lock = threading.Lock()
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        self.cache_dir = os.path.join(appdata, "HELXAID", "lyrics_cache")
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
        except Exception:
            pass

    def _hash_key(self, title: str, artist: str, duration: Any) -> str:
        dur_val = 0
        if duration is not None:
            if isinstance(duration, (int, float)):
                try:
                    dur_val = round(duration)
                except Exception:
                    dur_val = 0
            elif isinstance(duration, str):
                d_str = duration.strip()
                if ":" in d_str:
                    try:
                        parts = [float(p) for p in d_str.split(":") if p.strip()]
                        if len(parts) == 2:
                            dur_val = round(parts[0] * 60 + parts[1])
                        elif len(parts) == 3:
                            dur_val = round(parts[0] * 3600 + parts[1] * 60 + parts[2])
                    except Exception:
                        dur_val = 0
                else:
                    try:
                        dur_val = round(float(d_str))
                    except Exception:
                        dur_val = 0
        t_clean = LyricQuerySanitizer.clean_title(title).lower().strip()
        a_clean = LyricQuerySanitizer.clean_artist(artist).lower().strip()
        raw = f"{t_clean}|{a_clean}|{dur_val}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    def get(self, title: str, artist: str, duration: float) -> Optional[LyricData]:
        key = self._hash_key(title, artist, duration)
        file_path = os.path.join(self.cache_dir, f"{key}.json")
        with self._lock:
            if not os.path.exists(file_path):
                return None
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                lines = [
                    LyricLine(
                        time_ms=l['time_ms'],
                        text=l['text'],
                        translation=l.get('translation'),
                        romaji=l.get('romaji'),
                        google_romaji=l.get('google_romaji'),
                        genius_romaji=l.get('genius_romaji'),
                        netease_romaji=l.get('netease_romaji'),
                        raw_translation=l.get('raw_translation')
                    ) for l in data.get('lines', [])
                ]
                if not lines:
                    return None
                res = LyricData(
                    is_synced=data.get('is_synced', False),
                    lines=lines,
                    source=data.get('source', 'Cached (LRCLIB)'),
                    title=data.get('title', title),
                    artist=data.get('artist', artist),
                    album=data.get('album', ''),
                    offset_ms=data.get('offset_ms', 0),
                    plain_text=data.get('plain_text', ''),
                    has_romaji=data.get('has_romaji', False) or any(bool(l.romaji or l.google_romaji) for l in lines),
                    has_google_romaji=data.get('has_google_romaji', False) or any(bool(l.google_romaji) for l in lines),
                    has_genius_romaji=data.get('has_genius_romaji', False) or any(bool(l.genius_romaji) for l in lines),
                    has_netease_romaji=data.get('has_netease_romaji', False) or any(bool(l.netease_romaji) for l in lines),
                    has_translation=data.get('has_translation', False) or any(bool(l.raw_translation) for l in lines),
                    genius_url=data.get('genius_url', ''),
                    romaji_status=data.get('romaji_status', 'none'),
                    romaji_attempt_ts=data.get('romaji_attempt_ts', 0.0)
                )
                if is_valid_lyric_content(res):
                    return res
            except Exception:
                return None
        return None

    def put(self, title: str, artist: str, duration: float, data: LyricData):
        if not data or not data.lines or not is_valid_lyric_content(data):
            return
        key = self._hash_key(title, artist, duration)
        file_path = os.path.join(self.cache_dir, f"{key}.json")
        tmp_path = f"{file_path}.{os.getpid()}_{threading.get_ident()}_{time.time_ns()}.tmp"
        try:
            payload = {
                'title': data.title,
                'artist': data.artist,
                'album': data.album,
                'is_synced': data.is_synced,
                'source': data.source,
                'offset_ms': data.offset_ms,
                'plain_text': data.plain_text,
                'has_romaji': getattr(data, 'has_romaji', False),
                'has_google_romaji': getattr(data, 'has_google_romaji', False),
                'has_genius_romaji': getattr(data, 'has_genius_romaji', False),
                'has_netease_romaji': getattr(data, 'has_netease_romaji', False),
                'has_translation': getattr(data, 'has_translation', False),
                'genius_url': getattr(data, 'genius_url', ''),
                'romaji_status': getattr(data, 'romaji_status', 'none'),
                'romaji_attempt_ts': getattr(data, 'romaji_attempt_ts', 0.0),
                'lines': [{
                    'time_ms': l.time_ms,
                    'text': l.text,
                    'translation': l.translation,
                    'romaji': getattr(l, 'romaji', None),
                    'google_romaji': getattr(l, 'google_romaji', None),
                    'genius_romaji': getattr(l, 'genius_romaji', None),
                    'netease_romaji': getattr(l, 'netease_romaji', None),
                    'raw_translation': getattr(l, 'raw_translation', None)
                } for l in data.lines]
            }
            with self._lock:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, file_path)
        except Exception:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    def delete(self, title: str, artist: str, duration: float):
        key = self._hash_key(title, artist, duration)
        file_path = os.path.join(self.cache_dir, f"{key}.json")
        with self._lock:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass


class LRCLibClient:
    """High-resilience client for LRCLIB open lyric database (https://lrclib.net/) with precision candidate scoring."""
    GENERIC_ARTISTS = LyricQuerySanitizer.GENERIC_ARTISTS
    USER_AGENT = "HELXAID-MusicPlayer/v1.0 (https://github.com/TDD131/HELXAID)"
    BASE_URL = "https://lrclib.net/api"

    @classmethod
    def clean_query_title(cls, title: str) -> str:
        return LyricQuerySanitizer.clean_title(title)

    @classmethod
    def clean_query_artist(cls, artist: str) -> str:
        return LyricQuerySanitizer.clean_artist(artist)

    @classmethod
    def split_artist_title(cls, raw_title: str) -> Tuple[str, str]:
        cands = LyricQuerySanitizer.extract_candidates(raw_title)
        if cands:
            return cands[0][1], cands[0][0]
        return "", LyricQuerySanitizer.clean_title(raw_title)

    @classmethod
    def _http_get(cls, url: str) -> Optional[Any]:
        req = urllib.request.Request(url, headers={'User-Agent': cls.USER_AGENT})
        ctx = ssl._create_unverified_context()
        try:
            with urllib.request.urlopen(req, timeout=3.5, context=ctx) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode('utf-8'))
        except Exception:
            pass
        return None

    @classmethod
    def fetch_lyrics(cls, title: str, artist: str = "", album: str = "", duration: Any = 0) -> Optional[LyricData]:
        dur_val = 0.0
        if duration is not None:
            if isinstance(duration, (int, float)):
                dur_val = float(duration)
            elif isinstance(duration, str):
                d_str = duration.strip()
                if ":" in d_str:
                    try:
                        parts = [float(p) for p in d_str.split(":") if p.strip()]
                        if len(parts) == 2:
                            dur_val = parts[0] * 60.0 + parts[1]
                        elif len(parts) == 3:
                            dur_val = parts[0] * 3600.0 + parts[1] * 60.0 + parts[2]
                    except Exception:
                        dur_val = 0.0
                else:
                    try:
                        dur_val = float(d_str)
                    except Exception:
                        dur_val = 0.0
        target_duration = dur_val

        candidates = LyricQuerySanitizer.extract_candidates(title, artist)
        if not candidates:
            return None

        # 1. Direct GET Queries
        for cand_t, cand_a in candidates:
            for use_dur in ([True, False] if target_duration > 0 else [False]):
                params = {'track_name': cand_t}
                if cand_a:
                    params['artist_name'] = cand_a
                if album:
                    params['album_name'] = album
                if use_dur and target_duration > 0:
                    params['duration'] = str(int(target_duration))

                url = f"{cls.BASE_URL}/get?{urllib.parse.urlencode(params)}"
                data = cls._http_get(url)
                if data and isinstance(data, dict):
                    t_name = data.get('trackName') or cand_t
                    a_name = data.get('artistName') or cand_a
                    synced = data.get('syncedLyrics')
                    plain = data.get('plainLyrics')
                    d_val = float(data.get('duration') or 0.0)
                    
                    score, is_qual = LyricMatchVerifier.score_candidate(
                        candidate_title=t_name,
                        candidate_artist=a_name,
                        candidate_duration_s=d_val,
                        target_title=cand_t,
                        target_artist=cand_a,
                        target_duration_s=target_duration,
                        has_synced=bool(synced)
                    )
                    if is_qual:
                        if synced:
                            res = LRCParser.parse(synced, title=t_name, artist=a_name)
                            res.source = "LRCLIB Online"
                            return res
                        elif plain:
                            res = LRCParser.parse(plain, title=t_name, artist=a_name)
                            res.source = "LRCLIB Online"
                            return res

        # 2. Search Queries Cascades with Strict Similarity Verification
        search_queries = []
        for cand_t, cand_a in candidates:
            if cand_a and cand_t:
                search_queries.append((f"{cand_a} {cand_t}".strip(), cand_t, cand_a))
            if cand_t:
                search_queries.append((cand_t, cand_t, cand_a))

        best_scored_item = None
        best_score = -1.0
        best_cand_t = ""
        best_cand_a = ""

        for q_str, cand_t, cand_a in search_queries:
            search_url = f"{cls.BASE_URL}/search?q={urllib.parse.quote(q_str)}"
            results = cls._http_get(search_url)
            if results and isinstance(results, list):
                for item in results:
                    if not isinstance(item, dict):
                        continue
                    synced = item.get('syncedLyrics')
                    plain = item.get('plainLyrics')
                    if not synced and not plain:
                        continue
                    t_name = item.get('trackName') or ""
                    a_name = item.get('artistName') or ""
                    d_val = float(item.get('duration') or 0.0)
                    
                    score, is_qual = LyricMatchVerifier.score_candidate(
                        candidate_title=t_name,
                        candidate_artist=a_name,
                        candidate_duration_s=d_val,
                        target_title=cand_t,
                        target_artist=cand_a,
                        target_duration_s=target_duration,
                        has_synced=bool(synced)
                    )
                    if is_qual and score > best_score:
                        best_score = score
                        best_scored_item = item
                        best_cand_t = cand_t
                        best_cand_a = cand_a

            if best_score >= 80.0 and best_scored_item and best_scored_item.get('syncedLyrics'):
                break

        if best_scored_item:
            synced = best_scored_item.get('syncedLyrics')
            plain = best_scored_item.get('plainLyrics')
            t_name = best_scored_item.get('trackName') or best_cand_t
            a_name = best_scored_item.get('artistName') or best_cand_a
            if synced:
                res = LRCParser.parse(synced, title=t_name, artist=a_name)
                res.source = "LRCLIB Online"
                return res
            elif plain:
                res = LRCParser.parse(plain, title=t_name, artist=a_name)
                res.source = "LRCLIB Online"
                return res

        return None


class NetEaseClient:
    """High-resilience client for NetEase Cloud Music (163.com) with Romaji/Translation merger and strict candidate scoring."""
    BASE_URL = "https://music.163.com/api"
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://music.163.com/',
        'Cookie': 'os=pc; osver=Microsoft-Windows-10-Professional-build-19045-64bit; appver=2.9.7.199837; channel=netease; __remember_me=true;'
    }

    @classmethod
    def _http_request(cls, url: str, data: dict = None) -> Optional[dict]:
        ctx = ssl._create_unverified_context()
        form_data = urllib.parse.urlencode(data).encode('utf-8') if data else None
        req = urllib.request.Request(url, data=form_data, headers=cls.HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=3.5, context=ctx) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode('utf-8'))
        except Exception:
            pass
        return None

    @classmethod
    def _search_best_song(cls, query: str, target_title: str, target_artist: str = "", target_duration: float = 0.0) -> Optional[dict]:
        if not query:
            return None
        search_url = f"{cls.BASE_URL}/search/get"
        payload = {'s': query, 'type': 1, 'offset': 0, 'limit': 8, 'total': 'true'}
        data = cls._http_request(search_url, payload)
        if not data or data.get('code') != 200:
            return None

        songs = data.get('result', {}).get('songs', [])
        if not songs:
            return None

        best_song = None
        best_score = -1.0

        for s in songs:
            s_name = s.get('name', '')
            s_artists = ', '.join(a.get('name', '') for a in s.get('artists', []))
            s_dur_s = (s.get('dt') or s.get('duration') or 0) / 1000.0

            score, is_qual = LyricMatchVerifier.score_candidate(
                candidate_title=s_name,
                candidate_artist=s_artists,
                candidate_duration_s=s_dur_s,
                target_title=target_title,
                target_artist=target_artist,
                target_duration_s=target_duration,
                has_synced=True
            )

            if is_qual and score > best_score:
                best_score = score
                best_song = s

        return best_song

    @classmethod
    def fetch_lyrics(cls, title: str, artist: str = "", album: str = "", duration: float = 0) -> Optional[LyricData]:
        candidates = LyricQuerySanitizer.extract_candidates(title, artist)
        if not candidates:
            return None

        song_info = None
        target_t = ""
        target_a = ""

        for cand_t, cand_a in candidates:
            queries = []
            if cand_a and cand_t:
                queries.append(f"{cand_a} {cand_t}")
            if cand_t:
                queries.append(cand_t)

            for q in queries:
                song_info = cls._search_best_song(q, target_title=cand_t, target_artist=cand_a, target_duration=duration)
                if song_info:
                    target_t = cand_t
                    target_a = cand_a
                    break
            if song_info:
                break

        if not song_info:
            return None

        song_id = song_info.get('id')
        matched_title = song_info.get('name', target_t)
        matched_artists = ', '.join(a.get('name', '') for a in song_info.get('artists', [])) or target_a

        lrc_url = f"{cls.BASE_URL}/song/lyric?os=pc&id={song_id}&lv=-1&kv=-1&tv=-1"
        lrc_data = cls._http_request(lrc_url)
        if not lrc_data:
            return None

        raw_lrc = lrc_data.get('lrc', {}).get('lyric', '')
        if not raw_lrc or not raw_lrc.strip():
            return None

        parsed = LRCParser.parse(raw_lrc, title=matched_title, artist=matched_artists)
        parsed.source = "NetEase Online"

        raw_roma = lrc_data.get('romalrc', {}).get('lyric', '')
        raw_trans = lrc_data.get('tlyric', {}).get('lyric', '')

        if raw_roma:
            parsed_roma = LRCParser.parse(raw_roma)
            cls._merge_romaji(parsed.lines, parsed_roma.lines)
            parsed.has_romaji = True
            parsed.has_netease_romaji = True

        if raw_trans:
            parsed_trans = LRCParser.parse(raw_trans)
            cls._merge_translation(parsed.lines, parsed_trans.lines)
            parsed.has_translation = True

        # Default active translation is romaji if present, otherwise raw_translation
        for m in parsed.lines:
            if m.romaji:
                m.translation = m.romaji
            elif m.raw_translation:
                m.translation = m.raw_translation

        return parsed

    @classmethod
    def _merge_romaji(cls, main_lines: list, roma_lines: list):
        """Align Romaji pronunciation stream to main lyric timestamps within 150ms."""
        if not roma_lines:
            return
        roma_dict = {l.time_ms: l.text for l in roma_lines if l.time_ms >= 0}
        roma_times = sorted(roma_dict.keys())
        for m in main_lines:
            if m.time_ms < 0:
                continue
            idx = bisect.bisect_left(roma_times, m.time_ms)
            for c_idx in (idx - 1, idx, idx + 1):
                if 0 <= c_idx < len(roma_times):
                    t = roma_times[c_idx]
                    if abs(t - m.time_ms) <= 150:
                        m.romaji = roma_dict[t]
                        m.netease_romaji = roma_dict[t]
                        break

    @classmethod
    def _merge_translation(cls, main_lines: list, trans_lines: list):
        """Align translation stream (Chinese/etc.) to main lyric timestamps within 150ms."""
        if not trans_lines:
            return
        trans_dict = {l.time_ms: l.text for l in trans_lines if l.time_ms >= 0}
        trans_times = sorted(trans_dict.keys())
        for m in main_lines:
            if m.time_ms < 0:
                continue
            idx = bisect.bisect_left(trans_times, m.time_ms)
            for c_idx in (idx - 1, idx, idx + 1):
                if 0 <= c_idx < len(trans_times):
                    t = trans_times[c_idx]
                    if abs(t - m.time_ms) <= 150:
                        m.raw_translation = trans_dict[t]
                        break

    @classmethod
    def _merge_subtitles(cls, main_lines: list, sub_lines: list):
        """Align subtitle lines (Romaji or translation) to main lyric timestamps within 150ms."""
        cls._merge_romaji(main_lines, sub_lines)
        for m in main_lines:
            if m.romaji and not m.translation:
                m.translation = m.romaji

    @classmethod
    def enrich_lyrics(cls, data: LyricData, title: str = "", artist: str = "", duration: float = 0.0, cancellation_check: Optional[Callable[[], bool]] = None) -> bool:
        """
        Enriches LyricData in-place with NetEase Cloud timed Romaji and Chinese Translation.
        """
        if not data or not data.lines:
            return False
        if cancellation_check and cancellation_check():
            return False

        t_search = title or data.title
        a_search = artist or data.artist
        candidates = LyricQuerySanitizer.extract_candidates(t_search, a_search)
        if not candidates:
            return False

        song_info = None
        for cand_t, cand_a in candidates:
            if cancellation_check and cancellation_check():
                return False
            queries = []
            if cand_a and cand_t:
                queries.append(f"{cand_a} {cand_t}")
            if cand_t:
                queries.append(cand_t)
            for q in queries:
                song_info = cls._search_best_song(q, target_title=cand_t, target_artist=cand_a, target_duration=duration)
                if song_info:
                    break
            if song_info:
                break

        if not song_info:
            return False

        song_id = song_info.get('id')
        lrc_url = f"{cls.BASE_URL}/song/lyric?os=pc&id={song_id}&lv=-1&kv=-1&tv=-1"
        lrc_data = cls._http_request(lrc_url)
        if not lrc_data:
            return False

        raw_roma = lrc_data.get('romalrc', {}).get('lyric', '')
        raw_trans = lrc_data.get('tlyric', {}).get('lyric', '')
        enriched = False

        if raw_roma and raw_roma.strip():
            parsed_roma = LRCParser.parse(raw_roma)
            cls._merge_romaji(data.lines, parsed_roma.lines)
            data.has_romaji = True
            data.has_netease_romaji = True
            enriched = True

        if raw_trans and raw_trans.strip():
            parsed_trans = LRCParser.parse(raw_trans)
            cls._merge_translation(data.lines, parsed_trans.lines)
            data.has_translation = True
            enriched = True

        if enriched:
            print(f"[Lyrics] Successfully enriched '{data.title}' with NetEase Romaji/Translation")
            return True
        return False


class MusixmatchClient:
    """Client for Musixmatch Desktop API with strict candidate verification."""
    BASE_URL = "https://apic-desktop.musixmatch.com/ws/1.1"
    APP_ID = "web-desktop-app-v1.0"
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Cookie': 'AWSELB=dummy'
    }
    _cached_token = None
    _token_timestamp = 0.0

    @classmethod
    def _http_get(cls, url: str) -> Optional[dict]:
        ctx = ssl._create_unverified_context()
        req = urllib.request.Request(url, headers=cls.HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=3.5, context=ctx) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode('utf-8'))
        except Exception:
            pass
        return None

    @classmethod
    def _get_user_token(cls) -> Optional[str]:
        now = time.time()
        if cls._cached_token and (now - cls._token_timestamp < 1800):
            return cls._cached_token
        url = f"{cls.BASE_URL}/token.get?app_id={cls.APP_ID}"
        data = cls._http_get(url)
        if data:
            token = data.get('message', {}).get('body', {}).get('user_token')
            if token:
                cls._cached_token = token
                cls._token_timestamp = now
                return token
        return None

    @classmethod
    def fetch_lyrics(cls, title: str, artist: str = "", album: str = "", duration: float = 0) -> Optional[LyricData]:
        token = cls._get_user_token()
        if not token:
            return None

        candidates = LyricQuerySanitizer.extract_candidates(title, artist)
        if not candidates:
            return None

        best_track = None
        best_score = -1.0
        best_target_t = ""
        best_target_a = ""

        for cand_t, cand_a in candidates:
            params = {
                'app_id': cls.APP_ID,
                'usertoken': token,
                'q_track': cand_t,
                'f_has_lyrics': '1',
                'page_size': '6'
            }
            if cand_a:
                params['q_artist'] = cand_a

            s_url = f"{cls.BASE_URL}/track.search?{urllib.parse.urlencode(params)}"
            s_data = cls._http_get(s_url)
            if not s_data:
                continue

            track_list = s_data.get('message', {}).get('body', {}).get('track_list', [])
            for tr_item in track_list:
                tr = tr_item.get('track', {})
                tr_title = tr.get('track_name', '')
                tr_artist = tr.get('artist_name', '')
                tr_dur = float(tr.get('track_length') or 0.0)
                has_sub = bool(tr.get('has_subtitles'))

                score, is_qual = LyricMatchVerifier.score_candidate(
                    candidate_title=tr_title,
                    candidate_artist=tr_artist,
                    candidate_duration_s=tr_dur,
                    target_title=cand_t,
                    target_artist=cand_a,
                    target_duration_s=duration,
                    has_synced=has_sub
                )
                if is_qual and score > best_score:
                    best_score = score
                    best_track = tr
                    best_target_t = cand_t
                    best_target_a = cand_a

            if best_score >= 80.0:
                break

        if not best_track:
            return None

        cid = best_track.get('commontrack_id')
        if not cid:
            return None

        matched_title = best_track.get('track_name', best_target_t)
        matched_artist = best_track.get('artist_name', best_target_a)

        sub_params = {
            'app_id': cls.APP_ID,
            'usertoken': token,
            'commontrack_id': str(cid),
            'subtitle_format': 'lrc'
        }
        sub_url = f"{cls.BASE_URL}/track.subtitle.get?{urllib.parse.urlencode(sub_params)}"
        sub_data = cls._http_get(sub_url)
        if not sub_data:
            return None

        body = sub_data.get('message', {}).get('body', {}).get('subtitle', {}).get('subtitle_body', '')
        if body:
            parsed = LRCParser.parse(body, title=matched_title, artist=matched_artist)
            parsed.source = "Musixmatch Online"
            return parsed
        return None


class EmbeddedTagReader:
    """Extracts metadata lyrics from MP3 (ID3), MP4/M4A atoms, and FLAC/OGG files."""

    @classmethod
    def extract_lyrics(cls, file_path: str, title: str = "", artist: str = "") -> Optional[LyricData]:
        if not file_path or not os.path.exists(file_path):
            return None

        try:
            import mutagen
            audio = mutagen.File(file_path)
            if audio is not None:
                # 1. MP4 / M4A atoms
                if hasattr(audio, 'tags') and audio.tags:
                    for tag_key in ('\xa9lyr', '----:com.apple.iTunes:LYRICS', 'lyrics'):
                        if tag_key in audio.tags:
                            raw = audio.tags[tag_key]
                            text = raw[0] if isinstance(raw, list) else str(raw)
                            if text.strip():
                                res = LRCParser.parse(text, title=title, artist=artist)
                                res.source = "Embedded Tag"
                                return res

                # 2. ID3 tags (MP3)
                if hasattr(audio, 'tags') and audio.tags:
                    for key in audio.tags.keys():
                        if key.startswith('USLT') or key.startswith('SYLT'):
                            tag_text = str(audio.tags[key])
                            if tag_text.strip():
                                res = LRCParser.parse(tag_text, title=title, artist=artist)
                                res.source = "Embedded Tag"
                                return res

                # 3. Vorbis comments (FLAC / OGG / Opus)
                if hasattr(audio, 'get'):
                    for k in ('lyrics', 'unsyncedlyrics', 'synchronizedlyrics'):
                        val = audio.get(k)
                        if val:
                            raw = val[0] if isinstance(val, list) else str(val)
                            if raw.strip():
                                res = LRCParser.parse(raw, title=title, artist=artist)
                                res.source = "Embedded Tag"
                                return res
        except Exception:
            pass

        return None


class GeniusClient:
    """High-resilience client and scraper for Genius.com Romanized lyrics with strict validation."""
    SEARCH_URL = "https://genius.com/api/search/multi"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    HEADERS = {
        'User-Agent': USER_AGENT,
        'Accept': 'application/json, text/html, */*',
        'Accept-Language': 'en-US,en;q=0.9,ja;q=0.8',
        'Referer': 'https://genius.com/'
    }

    CONTAINER_REGEX = re.compile(r'<div[^>]*data-lyrics-container="true"[^>]*>(.*?)</div>', re.DOTALL)
    TAG_REGEX = re.compile(r'<.*?>')
    BR_REGEX = re.compile(r'<br\s*/?>', re.IGNORECASE)
    SECTION_HEADER_REGEX = re.compile(r'^\[.*?\]$')
    CONTRIBUTOR_HEADER_REGEX = re.compile(r'^\d+\s*Contributors.*', re.IGNORECASE)
    TRANSLATIONS_HEADER_REGEX = re.compile(r'^(Translations|Translations\w+|Embed).*', re.IGNORECASE)

    @classmethod
    def _http_get_json(cls, url: str) -> Optional[dict]:
        ctx = ssl._create_unverified_context()
        req = urllib.request.Request(url, headers=cls.HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=3.5, context=ctx) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode('utf-8'))
        except Exception:
            pass
        return None

    @classmethod
    def _http_get_html(cls, url: str) -> Optional[str]:
        ctx = ssl._create_unverified_context()
        req = urllib.request.Request(url, headers=cls.HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                if resp.status == 200:
                    return resp.read().decode('utf-8', errors='ignore')
        except Exception:
            pass
        return None

    @classmethod
    def search_romanized_url(cls, title: str, artist: str = "") -> Optional[Tuple[str, str]]:
        """
        Search Genius multi-search endpoint for the song's Romanized lyrics page.
        Returns: Tuple[song_url, song_title] or None
        """
        candidates = LyricQuerySanitizer.extract_candidates(title, artist)
        if not candidates:
            return None

        for cand_t, cand_a in candidates:
            queries: List[str] = []
            if cand_a and cand_t:
                queries.append(f"{cand_t} {cand_a} Romanized")
                queries.append(f"Genius Romanizations {cand_t} {cand_a}")
                queries.append(f"{cand_t} {cand_a}")
            if cand_t:
                queries.append(f"{cand_t} Romanized")
                queries.append(f"{cand_t} Romaji")

            for q in queries:
                url = f"{cls.SEARCH_URL}?q={urllib.parse.quote(q)}"
                data = cls._http_get_json(url)
                if not data:
                    continue

                sections = data.get('response', {}).get('sections', [])
                song_hits = []
                for sec in sections:
                    if sec.get('type') == 'song':
                        for hit in sec.get('hits', []):
                            res = hit.get('result', {})
                            if res and res.get('url'):
                                song_hits.append(res)

                if not song_hits:
                    continue

                def _score_hit(h: dict) -> Tuple[float, bool]:
                    full_t = (h.get('full_title') or '').lower()
                    t = (h.get('title') or '')
                    art = (h.get('primary_artist', {}).get('name') or '')

                    title_sim = LyricMatchVerifier.calculate_title_similarity(t, cand_t)
                    if title_sim < 0.40:
                        return 0.0, False

                    score = title_sim * 40.0
                    if 'romaniz' in full_t or 'romaji' in full_t:
                        score += 35.0
                    if 'genius romanizations' in art.lower() or 'genius romanizations' in full_t:
                        score += 25.0
                    if cand_a and LyricMatchVerifier.calculate_artist_similarity(art, cand_a) >= 0.60:
                        score += 20.0
                    return score, (title_sim >= 0.40 and score >= 40.0)

                scored_hits = []
                for hit in song_hits:
                    sc, is_qual = _score_hit(hit)
                    if is_qual:
                        scored_hits.append((sc, hit))

                if scored_hits:
                    scored_hits.sort(key=lambda x: x[0], reverse=True)
                    best_hit = scored_hits[0][1]
                    return best_hit.get('url'), best_hit.get('full_title', cand_t)

        return None

    @classmethod
    def fetch_romanized_lines(cls, url: str) -> List[str]:
        """
        Fetch HTML page and parse clean, ordered Romanized plain text lines.
        Strips HTML tags, section headers [Verse 1], contributors, and ads.
        """
        if not url:
            return []
        html_content = cls._http_get_html(url)
        if not html_content:
            return []

        containers = cls.CONTAINER_REGEX.findall(html_content)
        if not containers:
            return []

        all_text = ""
        for c in containers:
            c_clean = cls.BR_REGEX.sub('\n', c)
            c_clean = cls.TAG_REGEX.sub('', c_clean)
            c_clean = html.unescape(c_clean)
            all_text += "\n" + c_clean

        raw_lines = [l.strip() for l in all_text.splitlines() if l.strip()]
        clean_lines: List[str] = []
        for line in raw_lines:
            if cls.CONTRIBUTOR_HEADER_REGEX.match(line):
                continue
            if cls.TRANSLATIONS_HEADER_REGEX.match(line):
                continue
            if cls.SECTION_HEADER_REGEX.match(line):
                continue
            if line.lower() in ('you might also like', 'embed', 'lyrics'):
                continue
            line = re.sub(r'\d+Embed$', '', line).strip()
            if line:
                clean_lines.append(line)

        return clean_lines

    @classmethod
    def enrich_lyrics(cls, data: LyricData, title: str = "", artist: str = "", cancellation_check: Optional[Callable[[], bool]] = None) -> bool:
        """
        Enriches LyricData in-place with Genius.com Romanized lyrics.
        """
        if not data or not data.lines:
            return False
        if cancellation_check and cancellation_check():
            return False

        t_search = title or data.title
        a_search = artist or data.artist
        res = cls.search_romanized_url(t_search, a_search)
        if not res:
            return False

        if cancellation_check and cancellation_check():
            return False

        url, g_title = res
        g_lines = cls.fetch_romanized_lines(url)
        if not g_lines:
            return False

        success = RomajiAlignmentEngine.align_genius_romaji(data.lines, g_lines)
        if success:
            data.has_genius_romaji = True
            data.has_romaji = True
            data.genius_url = url
            print(f"[Lyrics] Successfully enriched '{data.title}' with Genius Romanized ({len(g_lines)} lines) from '{url}'")
            return True
        return False


def is_instrumental_line(text: Optional[str]) -> bool:
    """Check if text is an instrumental placeholder or music note marker."""
    if not text:
        return True
    t = text.strip()
    if not t:
        return True
    t_lower = t.lower()
    return t in ("♪", "♫", "♬", "---", "--", "...", "…") or t_lower in (
        "(instrumental)", "[instrumental]", "instrumental",
        "(music)", "[music]", "music",
        "(solo)", "[solo]", "solo",
        "(interlude)", "[interlude]", "interlude",
        "(intro)", "[intro]", "(outro)", "[outro]"
    )


class LocalKanaRomanizer:
    """Fast, pure-Python Hiragana and Katakana Hepburn transliterator for offline fallback."""
    COMPOUNDS = {
        'きゃ': 'kya', 'きゅ': 'kyu', 'きょ': 'kyo',
        'しゃ': 'sha', 'しゅ': 'shu', 'しょ': 'sho',
        'ちゃ': 'cha', 'ちゅ': 'chu', 'ちょ': 'cho',
        'にゃ': 'nya', 'にゅ': 'nyu', 'にょ': 'nyo',
        'ひゃ': 'hya', 'ひゅ': 'hyu', 'ひょ': 'hyo',
        'みゃ': 'mya', 'みゅ': 'myu', 'みょ': 'myo',
        'りゃ': 'rya', 'りゅ': 'ryu', 'りょ': 'ryo',
        'ぎゃ': 'gya', 'ぎゅ': 'gyu', 'ぎょ': 'gyo',
        'じゃ': 'ja',  'じゅ': 'ju',  'じょ': 'jo',
        'ぢゃ': 'ja',  'ぢゅ': 'ju',  'ぢょ': 'jo',
        'びゃ': 'bya', 'びゅ': 'byu', 'びょ': 'byo',
        'ぴゃ': 'pya', 'ぴゅ': 'pyu', 'ぴょ': 'pyo',
        'ふぁ': 'fa',  'ふぃ': 'fi',  'ふぇ': 'fe',  'ふぉ': 'fo',
        'てぃ': 'ti',  'でぃ': 'di',  'とぅ': 'tu',  'どぅ': 'du',
        'うぃ': 'wi',  'うぇ': 'we',  'うぉ': 'wo',
        'ヴぁ': 'va',  'ヴぃ': 'vi',  'ヴ': 'vu',   'ヴぇ': 've',  'ヴぉ': 'vo',
        'しぇ': 'she', 'じぇ': 'je',  'ちぇ': 'che',
        'つぁ': 'tsa', 'つぃ': 'tsi', 'つぇ': 'tse', 'つぉ': 'tso',
        'キャ': 'kya', 'キュ': 'kyu', 'キョ': 'kyo',
        'シャ': 'sha', 'シュ': 'shu', 'ショ': 'sho',
        'チャ': 'cha', 'チュ': 'chu', 'チョ': 'cho',
        'ニャ': 'nya', 'ニュ': 'nyu', 'ニョ': 'nyo',
        'ヒャ': 'hya', 'ヒュ': 'hyu', 'ヒョ': 'hyo',
        'ミャ': 'mya', 'ミュ': 'myu', 'ミョ': 'myo',
        'リャ': 'rya', 'リュ': 'ryu', 'リョ': 'ryo',
        'ギャ': 'gya', 'ギュ': 'gyu', 'ギョ': 'gyo',
        'ジャ': 'ja',  'ジュ': 'ju',  'ジョ': 'jo',
        'ヂャ': 'ja',  'ヂュ': 'ju',  'ヂョ': 'jo',
        'ビャ': 'bya', 'ビュ': 'byu', 'ビョ': 'byo',
        'ピャ': 'pya', 'ピュ': 'pyu', 'ピョ': 'pyo',
        'ファ': 'fa',  'フィ': 'fi',  'フェ': 'fe',  'フォ': 'fo',
        'ティ': 'ti',  'ディ': 'di',  'トゥ': 'tu',  'ドゥ': 'du',
        'ウィ': 'wi',  'ウェ': 'we',  'ウォ': 'wo',
        'シェ': 'she', 'ジェ': 'je',  'チェ': 'che',
        'ツァ': 'tsa', 'ツィ': 'tsi', 'ツェ': 'tse', 'ツォ': 'tso',
    }

    SINGLE = {
        'あ': 'a', 'い': 'i', 'う': 'u', 'え': 'e', 'お': 'o',
        'か': 'ka', 'き': 'ki', 'く': 'ku', 'け': 'ke', 'こ': 'ko',
        'さ': 'sa', 'し': 'shi', 'す': 'su', 'せ': 'se', 'そ': 'so',
        'た': 'ta', 'ち': 'chi', 'つ': 'tsu', 'て': 'te', 'と': 'to',
        'な': 'na', 'に': 'ni', 'ぬ': 'nu', 'ね': 'ne', 'の': 'no',
        'は': 'ha', 'ひ': 'hi', 'ふ': 'fu', 'へ': 'he', 'ほ': 'ho',
        'ま': 'ma', 'み': 'mi', 'む': 'mu', 'め': 'me', 'も': 'mo',
        'や': 'ya', 'ゆ': 'yu', 'よ': 'yo',
        'ら': 'ra', 'り': 'ri', 'る': 'ru', 'れ': 're', 'ろ': 'ro',
        'わ': 'wa', 'ゐ': 'wi', 'ゑ': 'we', 'を': 'o',  'ん': 'n',
        'が': 'ga', 'ぎ': 'gi', 'ぐ': 'gu', 'げ': 'ge', 'ご': 'go',
        'ざ': 'za', 'じ': 'ji', 'ず': 'zu', 'ぜ': 'ze', 'ぞ': 'zo',
        'だ': 'da', 'ぢ': 'ji', 'づ': 'zu', 'で': 'de', 'ど': 'do',
        'ば': 'ba', 'び': 'bi', 'ぶ': 'bu', 'べ': 'be', 'ぼ': 'bo',
        'ぱ': 'pa', 'ぴ': 'pi', 'ぷ': 'pu', 'ぺ': 'pe', 'ぽ': 'po',
        'ア': 'a', 'イ': 'i', 'ウ': 'u', 'エ': 'e', 'オ': 'o',
        'カ': 'ka', 'キ': 'ki', 'ク': 'ku', 'ケ': 'ke', 'コ': 'ko',
        'サ': 'sa', 'シ': 'shi', 'ス': 'su', 'セ': 'se', 'ソ': 'so',
        'タ': 'ta', 'チ': 'chi', 'ツ': 'tsu', 'テ': 'te', 'ト': 'to',
        'ナ': 'na', 'ニ': 'ni', 'ヌ': 'nu', 'ネ': 'ne', 'ノ': 'no',
        'ハ': 'ha', 'ヒ': 'hi', 'フ': 'fu', 'ヘ': 'he', 'ホ': 'ho',
        'マ': 'ma', 'ミ': 'mi', 'ム': 'mu', 'メ': 'me', 'モ': 'mo',
        'ヤ': 'ya', 'ユ': 'yu', 'ヨ': 'yo',
        'ラ': 'ra', 'リ': 'ri', 'ル': 'ru', 'レ': 're', 'ロ': 'ro',
        'ワ': 'wa', 'ヰ': 'wi', 'ヱ': 'we', 'ヲ': 'o',  'ン': 'n',
        'ガ': 'ga', 'ギ': 'gi', 'グ': 'gu', 'ゲ': 'ge', 'ご': 'go',
        'ザ': 'za', 'ジ': 'ji', 'ズ': 'zu', 'ゼ': 'ze', 'ゾ': 'zo',
        'ダ': 'da', 'ヂ': 'ji', 'ヅ': 'zu', 'デ': 'de', 'ド': 'do',
        'バ': 'ba', 'ビ': 'bi', 'ブ': 'bu', 'ベ': 'be', 'ボ': 'bo',
        'パ': 'pa', 'ピ': 'pi', 'プ': 'pu', 'ペ': 'pe', 'ポ': 'po',
    }

    VOWEL_MAP = {'a': 'ā', 'i': 'ī', 'u': 'ū', 'e': 'ē', 'o': 'ō'}
    KANA_REGEX = re.compile(r'[\u3040-\u30ff]')

    @classmethod
    def has_kana(cls, text: str) -> bool:
        return bool(cls.KANA_REGEX.search(text or ""))

    @classmethod
    def romanize(cls, text: str) -> str:
        if not text:
            return ""
        out = []
        i = 0
        n = len(text)
        sokuon = False

        while i < n:
            ch = text[i]

            if ch in ('っ', 'ッ'):
                sokuon = True
                i += 1
                continue

            if ch == 'ー':
                if out and out[-1] and out[-1][-1] in cls.VOWEL_MAP:
                    last_str = out[-1]
                    vowel = last_str[-1]
                    out[-1] = last_str[:-1] + cls.VOWEL_MAP[vowel]
                i += 1
                continue

            if i + 1 < n and text[i:i+2] in cls.COMPOUNDS:
                rom = cls.COMPOUNDS[text[i:i+2]]
                if sokuon:
                    lead = 't' if rom.startswith('ch') else rom[0]
                    rom = lead + rom
                    sokuon = False
                out.append(rom)
                i += 2
                continue

            if ch in cls.SINGLE:
                rom = cls.SINGLE[ch]
                if sokuon:
                    lead = 't' if rom.startswith('ch') else rom[0]
                    rom = lead + rom
                    sokuon = False
                out.append(rom)
                i += 1
                continue

            sokuon = False
            out.append(ch)
            i += 1

        return "".join(out)


class RomajiCircuitBreaker:
    """
    Thread-safe resilient multi-client circuit breaker protecting external transliteration endpoints.
    Tracks client-specific rate limits to support transparent failover across multiple API profiles.
    """
    CLIENT_POOL = ['dict-chrome-ex', 'at', 'tw-ob', 'it', 'gtrans', 'gtx']

    def __init__(self, initial_cooldown: float = 30.0, max_cooldown: float = 300.0):
        import threading
        self._lock = threading.Lock()
        self._client_cooldowns: Dict[str, float] = {}
        self._initial_cooldown = initial_cooldown
        self._max_cooldown = max_cooldown
        self._global_cooldown_until = 0.0
        self._consecutive_failures = 0

    def can_execute(self, client: Optional[str] = None) -> bool:
        with self._lock:
            now = time.time()
            if client:
                return now >= self._global_cooldown_until and self._client_cooldowns.get(client, 0.0) <= now
            if now < self._global_cooldown_until:
                return False
            available = [c for c in self.CLIENT_POOL if self._client_cooldowns.get(c, 0.0) <= now]
            return len(available) > 0

    def get_available_clients(self) -> List[str]:
        with self._lock:
            now = time.time()
            if now < self._global_cooldown_until:
                return []
            return [c for c in self.CLIENT_POOL if self._client_cooldowns.get(c, 0.0) <= now]

    def record_success(self, client: Optional[str] = None):
        with self._lock:
            if client:
                self._client_cooldowns.pop(client, None)
            else:
                self._client_cooldowns.clear()
            self._consecutive_failures = 0
            self._global_cooldown_until = 0.0

    def record_rate_limit(self, client: Optional[str] = None, retry_after: Optional[float] = None):
        with self._lock:
            now = time.time()
            dur = retry_after if (retry_after and retry_after > 0) else 60.0
            if client:
                self._client_cooldowns[client] = now + dur
                print(f"[Lyrics] Romaji client '{client}' rate-limited. Cooldown: {int(dur)}s")

            available = [c for c in self.CLIENT_POOL if self._client_cooldowns.get(c, 0.0) <= now]
            if not available:
                self._consecutive_failures += 1
                base_cd = min(self._initial_cooldown, dur) if retry_after else self._initial_cooldown
                global_dur = min(base_cd * (1.5 ** (self._consecutive_failures - 1)), self._max_cooldown)
                self._global_cooldown_until = now + global_dur
                print(f"[Lyrics] All Romaji clients rate-limited. Global cooldown: {int(global_dur)}s (until {time.strftime('%H:%M:%S', time.localtime(self._global_cooldown_until))})")

    def record_network_error(self, client: Optional[str] = None):
        with self._lock:
            now = time.time()
            if client:
                self._client_cooldowns[client] = now + 30.0
            else:
                self._consecutive_failures += 1
                if self._consecutive_failures >= 3:
                    self._global_cooldown_until = now + 45.0
                    print("[Lyrics] Romaji circuit breaker tripped (repetitive network errors). Cooldown: 45s")

    def get_remaining_cooldown(self) -> int:
        with self._lock:
            now = time.time()
            if now < self._global_cooldown_until:
                return max(0, int(self._global_cooldown_until - now))
            if self.CLIENT_POOL:
                earliest = min(self._client_cooldowns.get(c, 0.0) for c in self.CLIENT_POOL)
                if earliest > now:
                    return max(0, int(earliest - now))
            return 0

    def is_active(self) -> bool:
        return not self.can_execute()


class GoogleRomajiClient:
    """High-speed resilient client utilizing Google Translate's AI Romanization engine with client rotation and local fallback."""
    BASE_URLS = [
        "https://translate.googleapis.com/translate_a/single",
        "https://translate.google.com/translate_a/single"
    ]
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0"
    ]
    DELIMITER = " ⟦#⟧ "
    breaker = RomajiCircuitBreaker()

    @classmethod
    def _fetch_romaji_chunk(cls, text_chunk: str) -> Tuple[Optional[str], int]:
        """
        Fetches romaji transliteration for a single text chunk with client rotation.
        Returns: (romaji_text, http_status_code)
        """
        if not text_chunk or not text_chunk.strip():
            return None, 200

        available_clients = cls.breaker.get_available_clients()
        if not available_clients:
            return None, 429

        ctx = ssl.create_default_context()

        for client in available_clients:
            for base_url in cls.BASE_URLS:
                params = {
                    'client': client,
                    'sl': 'auto',
                    'tl': 'en',
                    'dt': 'rm',
                    'q': text_chunk
                }
                url = f"{base_url}?{urllib.parse.urlencode(params)}"
                ua = cls.USER_AGENTS[hash(client) % len(cls.USER_AGENTS)]
                req = urllib.request.Request(url, headers={
                    'User-Agent': ua,
                    'Accept': '*/*',
                    'Accept-Language': 'en-US,en;q=0.9,ja;q=0.8',
                    'Referer': 'https://translate.google.com/'
                })
                try:
                    with urllib.request.urlopen(req, timeout=3.5, context=ctx) as resp:
                        if resp.status == 200:
                            data = json.loads(resp.read().decode('utf-8'))
                            cls.breaker.record_success(client)
                            if data and isinstance(data, list) and data[0]:
                                last_item = data[0][-1]
                                if isinstance(last_item, list) and len(last_item) >= 4 and last_item[3]:
                                    return str(last_item[3]), 200
                            return None, 200
                except urllib.error.HTTPError as e:
                    if e.code == 429:
                        retry_after = None
                        try:
                            ra_hdr = e.headers.get('Retry-After')
                            if ra_hdr:
                                retry_after = float(ra_hdr)
                        except Exception:
                            pass
                        cls.breaker.record_rate_limit(client, retry_after)
                        break
                    elif e.code in (403, 503):
                        cls.breaker.record_rate_limit(client, 45.0)
                        break
                    else:
                        print(f"[Lyrics] Google Romaji HTTP error ({client}): {e}")
                except urllib.error.URLError as e:
                    cls.breaker.record_network_error(client)
                    print(f"[Lyrics] Google Romaji network error ({client}): {e}")
                    break
                except Exception as e:
                    print(f"[Lyrics] Google Romaji chunk fetch failed ({client}): {e}")

        return None, 429 if not cls.breaker.can_execute() else 500

    @classmethod
    def fetch_romaji_for_lines(cls, raw_lines: List[str], cancellation_check: Optional[Callable[[], bool]] = None) -> List[Optional[str]]:
        """
        Translates a list of plain lines to Romanized text via throttled batch chunking
        with automatic client rotation and local kana fallback.
        """
        if not raw_lines:
            return []

        results: List[Optional[str]] = [None] * len(raw_lines)
        CHUNK_SIZE = 35

        for i in range(0, len(raw_lines), CHUNK_SIZE):
            if cancellation_check and cancellation_check():
                print("[Lyrics] Google Romaji batch aborted: cancellation requested")
                return results

            chunk_slice = raw_lines[i:i + CHUNK_SIZE]
            joined = cls.DELIMITER.join(chunk_slice)
            romaji_raw, status = cls._fetch_romaji_chunk(joined)

            if romaji_raw:
                parts = re.split(r'\s*⟦#⟧\s*|\s*\|\s*\|\s*\|\s*', romaji_raw)
                if len(parts) == len(chunk_slice):
                    for j, part in enumerate(parts):
                        results[i + j] = parts[j].strip()
                else:
                    for j in range(min(len(parts), len(chunk_slice))):
                        results[i + j] = parts[j].strip()
            elif status == 429:
                break

            if i + CHUNK_SIZE < len(raw_lines):
                if cancellation_check and cancellation_check():
                    return results
                time.sleep(0.10)

        # Local Kana Romanization fallback for any missing lines with Japanese characters
        for idx, orig in enumerate(raw_lines):
            if not results[idx] and LocalKanaRomanizer.has_kana(orig):
                local_rom = LocalKanaRomanizer.romanize(orig).strip()
                if local_rom:
                    results[idx] = local_rom

        return results

    @classmethod
    def enrich_lyrics(cls, data: LyricData, cancellation_check: Optional[Callable[[], bool]] = None) -> bool:
        """
        Enriches LyricData in-place by attaching Google AI Romanized text to each LyricLine.
        Sets line.google_romaji, line.romaji, and fallback line.translation.
        """
        if not data or not data.lines:
            return False

        if cancellation_check and cancellation_check():
            return False

        # Filter out instrumental / placeholder lines for Romanization
        vocal_indices = []
        vocal_texts = []
        for idx, line in enumerate(data.lines):
            t = (line.text or "").strip()
            if t and not is_instrumental_line(t):
                vocal_indices.append(idx)
                vocal_texts.append(t)

        if not vocal_texts:
            return False

        romaji_results = cls.fetch_romaji_for_lines(vocal_texts, cancellation_check=cancellation_check)
        if not romaji_results:
            data.romaji_attempt_ts = time.time()
            data.romaji_status = "rate_limited" if cls.breaker.is_active() else "failed"
            return False

        enriched_count = 0
        for i, line_idx in enumerate(vocal_indices):
            roma = romaji_results[i]
            if roma:
                data.lines[line_idx].google_romaji = roma
                if not data.lines[line_idx].romaji:
                    data.lines[line_idx].romaji = roma
                if not data.lines[line_idx].translation:
                    data.lines[line_idx].translation = roma
                enriched_count += 1

        data.romaji_attempt_ts = time.time()
        if enriched_count > 0:
            data.has_google_romaji = True
            data.has_romaji = True
            data.romaji_status = "available"
            print(f"[Lyrics] Successfully enriched '{data.title}' with Google AI Romaji ({enriched_count} lines)")
            return True

        data.romaji_status = "rate_limited" if cls.breaker.is_active() else "failed"
        return False


class RomajiAlignmentEngine:
    """
    Intelligent alignment engine connecting unsynced Genius romanized lines
    to timestamped primary LyricLine objects.
    """

    @classmethod
    def align_genius_romaji(cls, timed_lines: List[LyricLine], genius_lines: List[str]) -> bool:
        """
        Aligns plain genius_lines into timed_lines in-place by setting `line.genius_romaji`.
        Returns True if successful alignment was achieved, False otherwise.
        """
        if not timed_lines or not genius_lines:
            return False

        # Filter active timed cues (excluding empty/instrumental markers)
        valid_indices = []
        for idx, line in enumerate(timed_lines):
            t = (line.text or "").strip()
            if t and t not in ("♪", "---", "--", "...", "(Instrumental)", "[Instrumental]"):
                valid_indices.append(idx)

        if not valid_indices:
            return False

        num_genius = len(genius_lines)

        for i, line_idx in enumerate(valid_indices):
            if i < num_genius:
                g_text = genius_lines[i]
                timed_lines[line_idx].genius_romaji = g_text
                # Set fallback romaji and translation if not already set
                if not timed_lines[line_idx].romaji:
                    timed_lines[line_idx].romaji = g_text
                if not timed_lines[line_idx].translation:
                    timed_lines[line_idx].translation = g_text

        return True


def needs_cjk_romaji(title: str, lines: List[LyricLine]) -> bool:
    """Check if title or lyrics contain CJK characters (Hiragana, Katakana, Kanji, Hangul)."""
    cjk_regex = re.compile(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]')
    if cjk_regex.search(title or ""):
        return True
    sample = " ".join(l.text for l in lines[:15] if l and l.text)
    return bool(cjk_regex.search(sample))


class LyricsFetchWorker(QThread):
    """
    Asynchronous background worker executing multi-tier cascading lyrics resolution:
    Tier 1: Local .lrc
    Tier 2: Embedded Metadata Tags (ID3 / MP4 atoms / Vorbis)
    Tier 3: Persistent Local Disk Cache
    Tier 4-6: High-Speed Parallel Online Race (LRCLIB + Musixmatch + NetEase)
    Enrichment: Background Non-Blocking Google AI Romaji & Genius.com Romanized Alignment
    """
    lyricsReady = Signal(int, object)  # (request_id, LyricData)

    def __init__(self, request_id: int, track: Dict[str, Any], cache_mgr: LyricsCacheManager, provider: str = "auto", parent=None):
        super().__init__(parent)
        self.request_id = request_id
        self.track = track
        self.cache_mgr = cache_mgr
        self.provider = (provider or "auto").lower().strip()
        self._is_cancelled = False

    def cancel(self):
        """Signal this worker and any associated background enrichment to abort immediately."""
        self._is_cancelled = True

    def is_cancelled(self) -> bool:
        return self._is_cancelled

    def _enrich_with_google_romaji(self, data: LyricData, title: str, artist: str):
        """Enrich LyricData with Google AI Romanized lines for CJK / non-Latin lyrics."""
        if self._is_cancelled or not data or not data.lines:
            return
        if getattr(data, 'has_google_romaji', False):
            return
        if not needs_cjk_romaji(title, data.lines):
            return

        # Check negative cache cooldown: if failed or rate_limited recently, skip
        romaji_status = getattr(data, 'romaji_status', 'none')
        attempt_ts = getattr(data, 'romaji_attempt_ts', 0.0)
        now = time.time()
        if romaji_status == "rate_limited" and (now - attempt_ts < 30.0):
            return
        if romaji_status == "failed" and (now - attempt_ts < 120.0):
            return

        try:
            success = GoogleRomajiClient.enrich_lyrics(data, cancellation_check=self.is_cancelled)
            if success and not self._is_cancelled:
                self.cache_mgr.put(title, artist, self.track.get('duration', 0.0), data)
                self.lyricsReady.emit(self.request_id, data)
            elif not success and not self._is_cancelled:
                self.cache_mgr.put(title, artist, self.track.get('duration', 0.0), data)
        except Exception as e:
            print(f"[Lyrics] Google Romaji enrichment notice for '{title}': {e}")

    def _enrich_with_genius_romaji(self, data: LyricData, title: str, artist: str):
        """Enrich LyricData with Genius Romanized lines only if track actually contains CJK lyrics."""
        if self._is_cancelled or not data or not data.lines:
            return
        if getattr(data, 'has_genius_romaji', False):
            return
        if not needs_cjk_romaji(title, data.lines):
            return

        try:
            success = GeniusClient.enrich_lyrics(data, title, artist, cancellation_check=self.is_cancelled)
            if success and not self._is_cancelled:
                self.cache_mgr.put(title, artist, self.track.get('duration', 0.0), data)
                self.lyricsReady.emit(self.request_id, data)
        except Exception as e:
            print(f"[Lyrics] Genius enrichment failed for '{title}': {e}")

    def _enrich_with_netease(self, data: LyricData, title: str, artist: str):
        """Enrich LyricData with NetEase timed Romaji and Chinese Translation if available."""
        if self._is_cancelled or not data or not data.lines:
            return
        if getattr(data, 'has_netease_romaji', False) and getattr(data, 'has_translation', False):
            return

        try:
            dur = self.track.get('duration', 0.0)
            success = NetEaseClient.enrich_lyrics(data, title, artist, duration=dur, cancellation_check=self.is_cancelled)
            if success and not self._is_cancelled:
                self.cache_mgr.put(title, artist, dur, data)
                self.lyricsReady.emit(self.request_id, data)
        except Exception as e:
            print(f"[Lyrics] NetEase enrichment notice for '{title}': {e}")

    def run(self):
        title = self.track.get('title', 'Unknown')
        artist = self.track.get('artist', '')
        album = self.track.get('album', '')
        raw_dur = self.track.get('duration', 0.0)
        file_path = self.track.get('path', '')

        dur_val = 0.0
        if raw_dur is not None:
            if isinstance(raw_dur, (int, float)):
                dur_val = float(raw_dur)
            elif isinstance(raw_dur, str):
                d_str = raw_dur.strip()
                if ":" in d_str:
                    try:
                        parts = [float(p) for p in d_str.split(":") if p.strip()]
                        if len(parts) == 2:
                            dur_val = parts[0] * 60.0 + parts[1]
                        elif len(parts) == 3:
                            dur_val = parts[0] * 3600.0 + parts[1] * 60.0 + parts[2]
                    except Exception:
                        dur_val = 0.0
                else:
                    try:
                        dur_val = float(d_str)
                    except Exception:
                        dur_val = 0.0
        duration = dur_val

        if self.provider == "local":
            # Direct Local .lrc
            if file_path and os.path.exists(file_path):
                base_path = os.path.splitext(file_path)[0]
                lrc_path = base_path + ".lrc"
                if os.path.exists(lrc_path):
                    try:
                        with open(lrc_path, "r", encoding="utf-8", errors="ignore") as f:
                            lrc_content = f.read()
                        data = LRCParser.parse(lrc_content, title=title, artist=artist)
                        data.source = "Local .LRC"
                        print(f"[Lyrics] Found local .lrc for '{title}' ({len(data.lines)} lines)")
                        self.lyricsReady.emit(self.request_id, data)
                        return
                    except Exception:
                        pass
                # Embedded Tags
                tag_data = EmbeddedTagReader.extract_lyrics(file_path, title=title, artist=artist)
                if tag_data and tag_data.lines:
                    print(f"[Lyrics] Extracted embedded tags for '{title}' ({len(tag_data.lines)} lines)")
                    self.lyricsReady.emit(self.request_id, tag_data)
                    return

            empty_data = LyricData(
                is_synced=False,
                lines=[LyricLine(time_ms=-1, text="♪ No Local Lyrics / Tags Found ♪")],
                source="none",
                title=title,
                artist=artist,
                plain_text=""
            )
            self.lyricsReady.emit(self.request_id, empty_data)
            return

        elif self.provider == "musixmatch":
            print(f"[Lyrics] Manual Fetch (Musixmatch) for '{title}' (Artist: '{artist}')...")
            online_data = MusixmatchClient.fetch_lyrics(title, artist, album, duration)
            if not online_data and file_path:
                for f_artist in self._extract_folder_artist_candidates(file_path):
                    online_data = MusixmatchClient.fetch_lyrics(title, f_artist, album, duration)
                    if online_data and online_data.lines:
                        break
            if online_data and online_data.lines:
                print(f"[Lyrics] Matched from [{online_data.source}] for '{title}'")
                self.cache_mgr.put(title, artist, duration, online_data)
                self.lyricsReady.emit(self.request_id, online_data)
                return

        elif self.provider == "netease":
            print(f"[Lyrics] Manual Fetch (NetEase) for '{title}' (Artist: '{artist}')...")
            online_data = NetEaseClient.fetch_lyrics(title, artist, album, duration)
            if not online_data and file_path:
                for f_artist in self._extract_folder_artist_candidates(file_path):
                    online_data = NetEaseClient.fetch_lyrics(title, f_artist, album, duration)
                    if online_data and online_data.lines:
                        break
            if online_data and online_data.lines:
                print(f"[Lyrics] Matched from [{online_data.source}] for '{title}'")
                self.cache_mgr.put(title, artist, duration, online_data)
                self.lyricsReady.emit(self.request_id, online_data)
                return

        elif self.provider == "lrclib":
            print(f"[Lyrics] Manual Fetch (LRCLIB) for '{title}' (Artist: '{artist}', Dur: {duration}s)...")
            online_data = LRCLibClient.fetch_lyrics(title, artist, album, duration)
            if not online_data and file_path:
                for f_artist in self._extract_folder_artist_candidates(file_path):
                    online_data = LRCLibClient.fetch_lyrics(title, f_artist, album, duration)
                    if online_data and online_data.lines:
                        break
            if online_data and online_data.lines:
                print(f"[Lyrics] Matched from [{online_data.source}] for '{title}'")
                self.cache_mgr.put(title, artist, duration, online_data)
                self.lyricsReady.emit(self.request_id, online_data)
                return

        else:
            # Step 1: Check Local .lrc in same directory (< 1ms)
            if file_path and os.path.exists(file_path):
                base_path = os.path.splitext(file_path)[0]
                lrc_path = base_path + ".lrc"
                if os.path.exists(lrc_path):
                    try:
                        with open(lrc_path, "r", encoding="utf-8", errors="ignore") as f:
                            lrc_content = f.read()
                        data = LRCParser.parse(lrc_content, title=title, artist=artist)
                        data.source = "Local .LRC"
                        print(f"[Lyrics] Found local .lrc for '{title}' ({len(data.lines)} lines)")
                        self.lyricsReady.emit(self.request_id, data)
                        return
                    except Exception:
                        pass

            # Step 2: Check Embedded ID3/FLAC/MP4 Metadata Tags (< 5ms)
            if file_path and os.path.exists(file_path):
                tag_data = EmbeddedTagReader.extract_lyrics(file_path, title=title, artist=artist)
                if tag_data and tag_data.lines:
                    print(f"[Lyrics] Extracted embedded tags for '{title}' ({len(tag_data.lines)} lines)")
                    self.lyricsReady.emit(self.request_id, tag_data)
                    return

            # Step 3: Check Local Disk Cache (< 1ms)
            cached = self.cache_mgr.get(title, artist, duration)
            if cached and cached.lines:
                print(f"[Lyrics] Loaded disk cache for '{title}' ({len(cached.lines)} lines)")
                self.lyricsReady.emit(self.request_id, cached)
                # If cached lyrics has CJK text but no Google Romaji yet, enrich in background
                if needs_cjk_romaji(title, cached.lines) and not getattr(cached, 'has_google_romaji', False):
                    romaji_status = getattr(cached, 'romaji_status', 'none')
                    attempt_ts = getattr(cached, 'romaji_attempt_ts', 0.0)
                    now = time.time()
                    should_enrich = True
                    if romaji_status == "rate_limited" and (now - attempt_ts < 30.0):
                        should_enrich = False
                    elif romaji_status == "failed" and (now - attempt_ts < 120.0):
                        should_enrich = False

                    if should_enrich and not self._is_cancelled:
                        import threading
                        def _bg_cached_enrich():
                            if not self._is_cancelled:
                                self._enrich_with_google_romaji(cached, title, artist)
                            if not self._is_cancelled:
                                self._enrich_with_genius_romaji(cached, title, artist)
                            if not self._is_cancelled:
                                self._enrich_with_netease(cached, title, artist)
                        threading.Thread(target=_bg_cached_enrich, daemon=True).start()
                return

            # Step 4-6: High-Speed Parallel Online Race across LRCLIB + Musixmatch + NetEase (~200ms - 400ms)
            import concurrent.futures
            online_data = None

            def _fetch_lrc():
                try: return LRCLibClient.fetch_lyrics(title, artist, album, duration)
                except Exception: return None

            def _fetch_mx():
                try: return MusixmatchClient.fetch_lyrics(title, artist, album, duration)
                except Exception: return None

            def _fetch_ne():
                try: return NetEaseClient.fetch_lyrics(title, artist, album, duration)
                except Exception: return None

            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                futures = {
                    executor.submit(_fetch_lrc): "LRCLIB",
                    executor.submit(_fetch_mx): "Musixmatch",
                    executor.submit(_fetch_ne): "NetEase"
                }
                candidates = []
                for f in concurrent.futures.as_completed(futures):
                    try:
                        cand = f.result()
                        if is_valid_lyric_content(cand):
                            if cand.is_synced:
                                online_data = cand
                                break
                            candidates.append(cand)
                    except Exception:
                        pass

                if not online_data and candidates:
                    online_data = candidates[0]

            # Fallback: Try Folder Directory Names as Candidate Artist if initial queries found nothing
            if not online_data and file_path:
                folder_candidates = self._extract_folder_artist_candidates(file_path)
                for f_artist in folder_candidates:
                    for client_fetch in [
                        lambda: LRCLibClient.fetch_lyrics(title, f_artist, album, duration),
                        lambda: MusixmatchClient.fetch_lyrics(title, f_artist, album, duration),
                        lambda: NetEaseClient.fetch_lyrics(title, f_artist, album, duration)
                    ]:
                        cand = client_fetch()
                        if is_valid_lyric_content(cand):
                            online_data = cand
                            break
                    if online_data:
                        break

            # Step 7: Tier 7 - Genius.com Scraper (Only if still nothing and CJK / Romanization or fallback)
            if not online_data:
                try:
                    res = GeniusClient.search_romanized_url(title, artist)
                    if res:
                        url, g_title = res
                        g_lines = GeniusClient.fetch_romanized_lines(url)
                        if g_lines:
                            g_data = LyricData(
                                is_synced=False,
                                lines=[LyricLine(time_ms=-1, text=line) for line in g_lines],
                                source="Genius",
                                title=g_title or title,
                                artist=artist,
                                plain_text="\n".join(g_lines),
                                genius_url=url
                            )
                            if is_valid_lyric_content(g_data):
                                online_data = g_data
                except Exception as e:
                    print(f"[Lyrics] Genius tier search notice: {e}")

            if online_data and online_data.lines:
                print(f"[Lyrics] Matched from [{online_data.source}] for '{title}' -> '{online_data.title}' by '{online_data.artist}' ({len(online_data.lines)} lines, synced={online_data.is_synced})")
                self.cache_mgr.put(title, artist, duration, online_data)
                self.lyricsReady.emit(self.request_id, online_data)
                
                # Asynchronously enrich with Google AI Romaji & Genius in background if CJK detected
                if needs_cjk_romaji(title, online_data.lines) and not self._is_cancelled:
                    import threading
                    def _bg_enrich():
                        if not self._is_cancelled:
                            self._enrich_with_google_romaji(online_data, title, artist)
                        if not self._is_cancelled:
                            self._enrich_with_genius_romaji(online_data, title, artist)
                        if not self._is_cancelled:
                            self._enrich_with_netease(online_data, title, artist)
                    threading.Thread(target=_bg_enrich, daemon=True).start()
                return

        print(f"[Lyrics] No lyrics found for '{title}' with provider '{self.provider}'")
        empty_data = LyricData(
            is_synced=False,
            lines=[LyricLine(time_ms=-1, text="♪ Instrumental / No Lyrics Available ♪")],
            source="none",
            title=title,
            artist=artist,
            plain_text=""
        )
        self.lyricsReady.emit(self.request_id, empty_data)

    @staticmethod
    def _extract_folder_artist_candidates(file_path: str) -> List[str]:
        """Extract potential artist names from parent or grandparent folder names."""
        GENERIC_FOLDERS = {
            'music', 'download', 'downloads', 'desktop', 'documents', 'songs', 'audio',
            'videos', 'video', 'media', 'new folder', 'temp', 'tmp', 'helxaid', 'python',
            'appdata', 'c:', 'd:', 'e:', 'f:', ''
        }
        candidates: List[str] = []
        if not file_path or not os.path.exists(file_path) or file_path.startswith(('http://', 'https://', 'ytsearch:', 'ytsearch1:', 'ytsearch6:')):
            return candidates
        try:
            dir_path = os.path.dirname(os.path.abspath(file_path))
            p1 = os.path.basename(dir_path).strip()
            if p1.lower() not in GENERIC_FOLDERS and not (len(p1) == 2 and p1[1] == ':'):
                candidates.append(p1)
            p2 = os.path.basename(os.path.dirname(dir_path)).strip()
            if p2.lower() not in GENERIC_FOLDERS and not (len(p2) == 2 and p2[1] == ':'):
                candidates.append(p2)
        except Exception:
            pass
        return candidates
