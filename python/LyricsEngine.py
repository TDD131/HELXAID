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
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
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
            
    # If the payload has fewer than 2 real lyric lines and total lines <= 6, it is metadata only
    if actual_lyric_lines < 2 and len(valid_lines) <= 6:
        return False
        
    return True


class LyricsCacheManager:
    """Manages persistent disk caching in %APPDATA%/HELXAID/lyrics_cache/."""

    def __init__(self):
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        self.cache_dir = os.path.join(appdata, "HELXAID", "lyrics_cache")
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
        except Exception:
            pass

    def _hash_key(self, title: str, artist: str, duration: float) -> str:
        raw = f"{title.lower().strip()}|{artist.lower().strip()}|{round(duration)}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    def get(self, title: str, artist: str, duration: float) -> Optional[LyricData]:
        key = self._hash_key(title, artist, duration)
        file_path = os.path.join(self.cache_dir, f"{key}.json")
        if os.path.exists(file_path):
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
                return LyricData(
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
                    genius_url=data.get('genius_url', '')
                )
            except Exception:
                return None
        return None

    def put(self, title: str, artist: str, duration: float, data: LyricData):
        if not data or not data.lines:
            return
        key = self._hash_key(title, artist, duration)
        file_path = os.path.join(self.cache_dir, f"{key}.json")
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
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
        except Exception:
            pass

    def delete(self, title: str, artist: str, duration: float):
        key = self._hash_key(title, artist, duration)
        file_path = os.path.join(self.cache_dir, f"{key}.json")
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass


class LRCLibClient:
    """High-resilience client for LRCLIB open lyric database (https://lrclib.net/)."""
    GENERIC_ARTISTS = {
        'single track', 'unknown', 'unknown artist', 'various', 'various artists',
        'n/a', 'none', '-', '--', 'undefined', 'audio', 'track', 'song', 'artist'
    }
    USER_AGENT = "HELXAID-MusicPlayer/v1.0 (https://github.com/TDD131/HELXAID)"
    BASE_URL = "https://lrclib.net/api"

    @classmethod
    def clean_query_title(cls, title: str) -> str:
        """Strip file extensions, leading numbers, and common YouTube/video/CJK tag clutter."""
        if not title:
            return ""
        t = re.sub(r'\.(mp4|mp3|mkv|webm|flac|wav|m4a|opus|ogg|aac|wma|mov|avi|m4v)$', '', title, flags=re.IGNORECASE)
        t = re.sub(r'^\d{1,3}\s*[-._]\s*', '', t)
        t = re.sub(r'^\d{1,3}\.\s*', '', t)
        # Strip lenticular, guillemets, and square brackets 【...】, ［...］, 《...》, 〈...〉
        t = re.sub(r'【.*?】|［.*?］|《.*?》|〈.*?〉', '', t)
        # Strip common video/audio suffixes in parentheses or brackets
        t = re.sub(r'(?i)\((?:official\s*)?(?:music\s*)?(?:video|audio|visualizer|lyric\s*video|lyrics|mv|pv|hd|4k|remaster(?:ed)?(?:\s*\d{4})?|live|acoustic|cover|full\s*song|original\s*song|clean|explicit|version|\d{2,3}k|kara|karaoke|off\s*vocal|on\s*vocal|instrumental|歌ってみた|covered\s+by).*?\)', '', t)
        t = re.sub(r'(?i)\[(?:official\s*)?(?:music\s*)?(?:video|audio|visualizer|lyric\s*video|lyrics|mv|pv|hd|4k|remaster(?:ed)?(?:\s*\d{4})?|live|acoustic|cover|full\s*song|original\s*song|clean|explicit|version|\d{2,3}k|kara|karaoke|off\s*vocal|on\s*vocal|instrumental|歌ってみた|covered\s+by).*?\]', '', t)
        t = re.sub(r'(?i)\b(official\s+video|official\s+audio|lyrics\s+video|music\s+video|hd|4k|remastered)\b', '', t)
        # Strip descriptive OST / battle theme / soundtrack suffixes after hyphen or colon
        t = re.sub(r'(?i)\s*[-—–:~]\s*.*?\b(?:battle\s*theme|main\s*theme|theme\s*song|theme|ost|soundtrack|insert\s*song|bgm)\b.*$', '', t)
        t = re.sub(r'[_]+', ' ', t)
        return t.strip(' -._')

    @classmethod
    def clean_query_artist(cls, artist: str) -> str:
        """Clean artist string and filter placeholder values."""
        if not artist or artist.lower().strip() in cls.GENERIC_ARTISTS:
            return ""
        a = re.sub(r'\[.*?\]|\(.*?\)|【.*?】', '', artist)
        a = re.sub(r'(?i)\b(topic|vevo)\b', '', a)
        a = re.sub(r'[_]+', ' ', a)
        return a.strip(' -._')

    @classmethod
    def split_artist_title(cls, raw_title: str) -> Tuple[str, str]:
        """Split artist and title supporting standard dashes and Japanese quote brackets 『...』 「...」."""
        # Pattern 1: Japanese Quotes (Artist - 「Title」 Extra or Artist 「Title」)
        m_quote = re.match(r'^(.*?)\s*[-—–:~]?\s*[「『](.*?)[」』](.*)$', raw_title.strip())
        if m_quote:
            artist_p = m_quote.group(1).strip(' -._')
            title_p = m_quote.group(2).strip(' -._')
            if title_p:
                return artist_p, title_p

        # Pattern 2: Separators with or without spaces
        separators = [' - ', ' -- ', ' — ', ' – ', ' : ', ' ~ ', ' -', '- ', '—', '–']
        for sep in separators:
            if sep in raw_title:
                parts = raw_title.split(sep, 1)
                left = parts[0].strip(' -._「」『』')
                right = parts[1].strip(' -._「」『』')
                if left and right:
                    return left, right
        return "", raw_title.strip(' -._「」『』')

    @classmethod
    def _http_get(cls, url: str) -> Optional[Any]:
        req = urllib.request.Request(url, headers={'User-Agent': cls.USER_AGENT})
        # SSL context fallback for environments with outdated root certs
        ctx = ssl._create_unverified_context()
        try:
            with urllib.request.urlopen(req, timeout=4.0, context=ctx) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode('utf-8'))
        except Exception:
            pass
        return None

    @classmethod
    def fetch_lyrics(cls, title: str, artist: str = "", album: str = "", duration: float = 0) -> Optional[LyricData]:
        c_title = cls.clean_query_title(title)
        c_artist = cls.clean_query_artist(artist)
        cand_artist, cand_title = cls.split_artist_title(c_title)

        if not c_title and not cand_title:
            return None

        # Build list of candidate (track_name, artist_name, use_duration) tuples to query directly
        direct_attempts: List[Tuple[str, str, bool]] = []

        if cand_artist and cand_title:
            direct_attempts.append((cand_title, cand_artist, True))
            direct_attempts.append((cand_title, cand_artist, False))

        if c_title and c_artist:
            direct_attempts.append((c_title, c_artist, True))
            direct_attempts.append((c_title, c_artist, False))

        if cand_artist and cand_title:
            # Try reversed pair just in case title was "Title - Artist"
            direct_attempts.append((cand_artist, cand_title, False))

        if c_title and not c_artist and not cand_artist:
            direct_attempts.append((c_title, "", False))

        fallback_plain: Optional[LyricData] = None

        # 1. Direct GET Queries
        for t_name, a_name, use_dur in direct_attempts:
            if not t_name:
                continue
            params = {'track_name': t_name}
            if a_name:
                params['artist_name'] = a_name
            if album:
                params['album_name'] = album
            if use_dur and duration > 0:
                params['duration'] = str(int(duration))

            url = f"{cls.BASE_URL}/get?{urllib.parse.urlencode(params)}"
            data = cls._http_get(url)
            if data:
                synced = data.get('syncedLyrics')
                plain = data.get('plainLyrics')
                if synced:
                    res = LRCParser.parse(synced, title=t_name, artist=a_name or c_artist)
                    res.source = "LRCLIB Online"
                    return res
                elif plain and not fallback_plain:
                    fallback_plain = LRCParser.parse(plain, title=t_name, artist=a_name or c_artist)
                    fallback_plain.source = "LRCLIB Online"

        # 2. Search Queries Cascades (Prefer Synced)
        search_terms: List[str] = []
        if cand_artist and cand_title:
            search_terms.append(f"{cand_artist} {cand_title}")
        if c_artist and c_title:
            search_terms.append(f"{c_artist} {c_title}")
        if cand_title:
            search_terms.append(cand_title)
        if c_title and c_title != cand_title:
            search_terms.append(c_title)

        for q in search_terms:
            search_url = f"{cls.BASE_URL}/search?q={urllib.parse.quote(q)}"
            results = cls._http_get(search_url)
            if results and isinstance(results, list):
                # Score results: heavily prefer syncedLyrics, match duration if available
                def _score_match(item):
                    score = 0
                    if item.get('syncedLyrics'):
                        score += 100
                    if duration > 0 and item.get('duration'):
                        diff = abs(float(item['duration']) - duration)
                        if diff <= 5:
                            score += 50
                        elif diff <= 15:
                            score += 20
                    return score

                sorted_results = sorted(results, key=_score_match, reverse=True)
                best = sorted_results[0]
                synced = best.get('syncedLyrics')
                plain = best.get('plainLyrics')
                t_name = best.get('trackName', cand_title or c_title)
                a_name = best.get('artistName', cand_artist or c_artist)
                if synced:
                    res = LRCParser.parse(synced, title=t_name, artist=a_name)
                    res.source = "LRCLIB Online"
                    return res
                elif plain and not fallback_plain:
                    fallback_plain = LRCParser.parse(plain, title=t_name, artist=a_name)
                    fallback_plain.source = "LRCLIB Online"

        # Return fallback plain text if found
        if fallback_plain:
            return fallback_plain

        # 3. Fallback Multi-Pass: Aggressive Base Song Title Stripping (for Live, Concert, Special Edits)
        # Strip all parentheses, brackets, Japanese brackets, and 'Live...' / 'at ...' suffixes
        base_t = re.sub(r'\(.*?\)|\[.*?\]|（.*?）|【.*?】', '', c_title)
        base_t = re.sub(r'(?i)\b(live\b.*|at\s+[A-Z].*)', '', base_t).strip(' -._')
        
        if base_t and base_t != c_title:
            b_artist, b_title = cls.split_artist_title(base_t)
            target_a = b_artist or cand_artist or c_artist
            target_t = b_title or base_t
            if target_t:
                # Direct GET attempt with base title
                b_params = {'track_name': target_t}
                if target_a:
                    b_params['artist_name'] = target_a
                b_url = f"{cls.BASE_URL}/get?{urllib.parse.urlencode(b_params)}"
                b_data = cls._http_get(b_url)
                if b_data:
                    synced = b_data.get('syncedLyrics')
                    plain = b_data.get('plainLyrics')
                    if synced:
                        res = LRCParser.parse(synced, title=target_t, artist=target_a)
                        res.source = "LRCLIB Online"
                        return res
                    elif plain:
                        res = LRCParser.parse(plain, title=target_t, artist=target_a)
                        res.source = "LRCLIB Online"
                        return res
                
                # Search attempt with base title
                b_search_q = f"{target_a} {target_t}".strip()
                b_search_url = f"{cls.BASE_URL}/search?q={urllib.parse.quote(b_search_q)}"
                b_results = cls._http_get(b_search_url)
                if b_results and isinstance(b_results, list):
                    synced_match = next((r for r in b_results if r.get('syncedLyrics')), None)
                    match = synced_match or b_results[0]
                    synced = match.get('syncedLyrics')
                    plain = match.get('plainLyrics')
                    if synced:
                        res = LRCParser.parse(synced, title=match.get('trackName', target_t), artist=match.get('artistName', target_a))
                        res.source = "LRCLIB Online"
                        return res
                    elif plain:
                        res = LRCParser.parse(plain, title=match.get('trackName', target_t), artist=match.get('artistName', target_a))
                        res.source = "LRCLIB Online"
                        return res

        return None


class NetEaseClient:
    """High-resilience client for NetEase Cloud Music (163.com) with Romaji/Translation merger."""
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
    def _search_song(cls, query: str) -> Optional[dict]:
        if not query:
            return None
        search_url = f"{cls.BASE_URL}/search/get"
        payload = {'s': query, 'type': 1, 'offset': 0, 'limit': 3, 'total': 'true'}
        data = cls._http_request(search_url, payload)
        if data and data.get('code') == 200:
            songs = data.get('result', {}).get('songs', [])
            if songs:
                return songs[0]
        return None

    @classmethod
    def fetch_lyrics(cls, title: str, artist: str = "", album: str = "", duration: float = 0) -> Optional[LyricData]:
        c_title = LRCLibClient.clean_query_title(title)
        c_artist = LRCLibClient.clean_query_artist(artist)
        cand_artist, cand_title = LRCLibClient.split_artist_title(c_title)

        target_a = cand_artist or c_artist
        target_t = cand_title or c_title
        if not target_t:
            return None

        # Try search queries
        queries = []
        if target_a and target_t:
            queries.append(f"{target_a} {target_t}")
        if target_t:
            queries.append(target_t)

        song_info = None
        for q in queries:
            song_info = cls._search_song(q)
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


class MusixmatchClient:
    """Client for Musixmatch Desktop API (Official Spotify/Apple Music Provider)."""
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
        c_title = LRCLibClient.clean_query_title(title)
        c_artist = LRCLibClient.clean_query_artist(artist)
        cand_artist, cand_title = LRCLibClient.split_artist_title(c_title)
        target_a = cand_artist or c_artist
        target_t = cand_title or c_title
        if not target_t:
            return None

        params = {
            'app_id': cls.APP_ID,
            'usertoken': token,
            'q_track': target_t,
            'f_has_lyrics': '1',
            'page_size': '3'
        }
        if target_a:
            params['q_artist'] = target_a

        s_url = f"{cls.BASE_URL}/track.search?{urllib.parse.urlencode(params)}"
        s_data = cls._http_get(s_url)
        if not s_data:
            return None

        track_list = s_data.get('message', {}).get('body', {}).get('track_list', [])
        if not track_list:
            return None

        best = track_list[0].get('track', {})
        cid = best.get('commontrack_id')
        if not cid:
            return None

        matched_title = best.get('track_name', target_t)
        matched_artist = best.get('artist_name', target_a)

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
    """High-resilience client and scraper for Genius.com Romanized lyrics."""
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
        c_title = LRCLibClient.clean_query_title(title)
        c_artist = LRCLibClient.clean_query_artist(artist)
        cand_artist, cand_title = LRCLibClient.split_artist_title(c_title)

        target_a = cand_artist or c_artist
        target_t = cand_title or c_title
        if not target_t:
            return None

        # Cascading search queries
        queries: List[str] = []
        if target_a and target_t:
            queries.append(f"{target_t} {target_a} Romanized")
            queries.append(f"Genius Romanizations {target_t} {target_a}")
            queries.append(f"{target_t} {target_a}")
        if target_t:
            queries.append(f"{target_t} Romanized")
            queries.append(f"{target_t} Romaji")

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

            # Prioritize hits that explicitly mention Romanized or Genius Romanizations
            def _score_hit(h: dict) -> int:
                score = 0
                full_t = (h.get('full_title') or '').lower()
                t = (h.get('title') or '').lower()
                art = (h.get('primary_artist', {}).get('name') or '').lower()

                if 'romaniz' in full_t or 'romaniz' in t or 'romaji' in full_t or 'romaji' in t:
                    score += 60
                if 'genius romanizations' in art or 'genius romanizations' in full_t:
                    score += 40
                if target_t.lower() in t or target_t.lower() in full_t:
                    score += 30
                if target_a and target_a.lower() in art:
                    score += 20
                return score

            sorted_hits = sorted(song_hits, key=_score_hit, reverse=True)
            best = sorted_hits[0]
            best_score = _score_hit(best)

            if best_score >= 30:
                return best.get('url'), best.get('full_title', target_t)

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


class GoogleRomajiClient:
    """High-speed client utilizing Google Translate's AI Romanization engine (dt=rm)."""
    BASE_URL = "https://translate.googleapis.com/translate_a/single"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    DELIMITER = " ||| "

    @classmethod
    def _fetch_romaji_chunk(cls, text_chunk: str) -> Optional[str]:
        if not text_chunk or not text_chunk.strip():
            return None
        params = {
            'client': 'gtx',
            'sl': 'auto',
            'tl': 'en',
            'dt': 'rm',
            'q': text_chunk
        }
        url = f"{cls.BASE_URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={'User-Agent': cls.USER_AGENT})
        ctx = ssl._create_unverified_context()
        try:
            with urllib.request.urlopen(req, timeout=4.5, context=ctx) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode('utf-8'))
                    if data and isinstance(data, list) and data[0]:
                        last_item = data[0][-1]
                        if isinstance(last_item, list) and len(last_item) >= 4 and last_item[3]:
                            return str(last_item[3])
        except Exception as e:
            print(f"[Lyrics] Google Romaji chunk fetch failed: {e}")
        return None

    @classmethod
    def fetch_romaji_for_lines(cls, raw_lines: List[str]) -> List[Optional[str]]:
        """
        Translates a list of plain lines to Romanized text via batch chunking.
        Returns a list of equal length to raw_lines.
        """
        if not raw_lines:
            return []

        results: List[Optional[str]] = [None] * len(raw_lines)
        CHUNK_SIZE = 25

        for i in range(0, len(raw_lines), CHUNK_SIZE):
            chunk_slice = raw_lines[i:i + CHUNK_SIZE]
            joined = cls.DELIMITER.join(chunk_slice)
            romaji_raw = cls._fetch_romaji_chunk(joined)
            if romaji_raw:
                # Split using regex delimiter pattern
                parts = re.split(r'\s*\|\s*\|\s*\|\s*', romaji_raw)
                if len(parts) == len(chunk_slice):
                    for j, part in enumerate(parts):
                        results[i + j] = parts[j].strip()
                else:
                    # Fallback: if split count mismatched, try line-by-line or assign sequentially
                    for j in range(min(len(parts), len(chunk_slice))):
                        results[i + j] = parts[j].strip()
            else:
                # If chunk failed completely, try individual lines for this chunk
                for j, single_l in enumerate(chunk_slice):
                    if single_l and single_l.strip():
                        single_roma = cls._fetch_romaji_chunk(single_l)
                        if single_roma:
                            results[i + j] = single_roma.strip()

        return results

    @classmethod
    def enrich_lyrics(cls, data: LyricData) -> bool:
        """
        Enriches LyricData in-place by attaching Google AI Romanized text to each LyricLine.
        Sets line.google_romaji, line.romaji, and fallback line.translation.
        """
        if not data or not data.lines:
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

        romaji_results = cls.fetch_romaji_for_lines(vocal_texts)
        if not romaji_results:
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

        if enriched_count > 0:
            data.has_google_romaji = True
            data.has_romaji = True
            print(f"[Lyrics] Successfully enriched '{data.title}' with Google AI Romaji ({enriched_count} lines)")
            return True

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

    def _enrich_with_google_romaji(self, data: LyricData, title: str, artist: str):
        """Enrich LyricData with Google AI Romanized lines for CJK / non-Latin lyrics."""
        if not data or not data.lines:
            return
        if getattr(data, 'has_google_romaji', False):
            return
        if not needs_cjk_romaji(title, data.lines):
            return

        try:
            success = GoogleRomajiClient.enrich_lyrics(data)
            if success:
                self.cache_mgr.put(title, artist, self.track.get('duration', 0.0), data)
                self.lyricsReady.emit(self.request_id, data)
        except Exception as e:
            print(f"[Lyrics] Google Romaji enrichment failed for '{title}': {e}")

    def _enrich_with_genius_romaji(self, data: LyricData, title: str, artist: str):
        """Enrich LyricData with Genius Romanized lines only if track actually contains CJK lyrics."""
        if not data or not data.lines:
            return
        if getattr(data, 'has_genius_romaji', False):
            return
        if not needs_cjk_romaji(title, data.lines):
            return

        try:
            res = GeniusClient.search_romanized_url(title, artist)
            if res:
                url, g_title = res
                g_lines = GeniusClient.fetch_romanized_lines(url)
                if g_lines:
                    success = RomajiAlignmentEngine.align_genius_romaji(data.lines, g_lines)
                    if success:
                        data.has_genius_romaji = True
                        data.has_romaji = True
                        data.genius_url = url
                        print(f"[Lyrics] Successfully enriched '{title}' with Genius Romanized ({len(g_lines)} lines) from '{url}'")
        except Exception as e:
            print(f"[Lyrics] Genius enrichment failed for '{title}': {e}")

    def run(self):
        title = self.track.get('title', 'Unknown')
        artist = self.track.get('artist', '')
        album = self.track.get('album', '')
        duration = self.track.get('duration', 0.0)
        file_path = self.track.get('path', '')

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
                    import threading
                    def _bg_cached_enrich():
                        self._enrich_with_google_romaji(cached, title, artist)
                        self._enrich_with_genius_romaji(cached, title, artist)
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
                if needs_cjk_romaji(title, online_data.lines):
                    import threading
                    def _bg_enrich():
                        self._enrich_with_google_romaji(online_data, title, artist)
                        self._enrich_with_genius_romaji(online_data, title, artist)
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
