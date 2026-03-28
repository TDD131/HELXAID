"""
Stress test for VLC download with checksum verification
"""
import os
import sys
import tempfile

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from integrations.tools_downloader import (
    download_vlc,
    download_file,
    calculate_checksum,
    CHECKSUMS,
    VLC_URLS,
)

def test_checksum_calculation():
    """Test checksum calculation function"""
    print("\n=== Test 1: Checksum Calculation ===")
    
    # Create a test file
    test_file = os.path.join(tempfile.gettempdir(), "test_checksum.txt")
    with open(test_file, 'w') as f:
        f.write("Hello, World!")
    
    try:
        checksum = calculate_checksum(test_file, "sha256")
        print(f"✓ Checksum calculated: {checksum}")
        print(f"✓ Checksum length: {len(checksum)} (expected: 64)")
        assert len(checksum) == 64, "Checksum should be 64 characters for SHA256"
        print("✓ Checksum calculation test PASSED")
        return True
    except Exception as e:
        print(f"✗ Checksum calculation test FAILED: {e}")
        return False
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)


def test_checksum_mismatch():
    """Test that download fails with wrong checksum"""
    print("\n=== Test 2: Checksum Mismatch Detection ===")
    
    # Download a small file with wrong checksum
    test_url = "https://get.videolan.org/vlc/3.0.20/win64/vlc-3.0.20-win64.zip"
    test_file = os.path.join(tempfile.gettempdir(), "vlc_test.zip")
    wrong_checksum = "0" * 64  # All zeros - definitely wrong
    
    try:
        print(f"Downloading from {test_url}...")
        success, error = download_file(
            test_url,
            test_file,
            expected_checksum=wrong_checksum,
            checksum_algorithm="sha256"
        )
        
        if not success:
            print(f"✓ Download correctly failed with checksum mismatch")
            print(f"✓ Error message: {error}")
            assert "checksum" in error.lower(), "Error should mention checksum"
            print("✓ Checksum mismatch detection test PASSED")
            return True
        else:
            print(f"✗ Download should have failed but succeeded")
            return False
    except Exception as e:
        print(f"✗ Checksum mismatch test FAILED: {e}")
        return False
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)


def test_vlc_urls():
    """Test that VLC URLs are accessible"""
    print("\n=== Test 3: VLC URL Accessibility ===")
    
    all_accessible = True
    for idx, url in enumerate(VLC_URLS):
        print(f"Testing URL {idx + 1}/{len(VLC_URLS)}: {url[:50]}...")
        try:
            # Just check if URL is accessible (HEAD request would be better but urllib doesn't support it easily)
            import urllib.request
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                method="HEAD"
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                print(f"  ✓ URL {idx + 1} accessible (HTTP {response.status})")
        except Exception as e:
            print(f"  ✗ URL {idx + 1} failed: {e}")
            all_accessible = False
    
    if all_accessible:
        print("✓ All VLC URLs accessible test PASSED")
    else:
        print("⚠ Some VLC URLs failed (this is expected for mirrors)")
    
    return all_accessible


def test_checksums_dict():
    """Test that CHECKSUMS dictionary is properly formatted"""
    print("\n=== Test 4: CHECKSUMS Dictionary Format ===")
    
    try:
        assert "vlc" in CHECKSUMS, "VLC checksum missing"
        assert len(CHECKSUMS["vlc"]) == 64, f"VLC checksum should be 64 chars, got {len(CHECKSUMS['vlc'])}"
        assert all(c in "0123456789abcdef" for c in CHECKSUMS["vlc"]), "VLC checksum should be hex"
        
        print(f"✓ VLC checksum present: {CHECKSUMS['vlc'][:16]}...")
        print(f"✓ Checksum length: 64 characters")
        print(f"✓ Checksum format: hexadecimal")
        print("✓ CHECKSUMS dictionary format test PASSED")
        return True
    except Exception as e:
        print(f"✗ CHECKSUMS dictionary test FAILED: {e}")
        return False


def test_download_with_correct_checksum():
    """Test actual VLC download with correct checksum"""
    print("\n=== Test 5: VLC Download with Correct Checksum ===")
    
    try:
        print("Starting VLC download (this may take a while)...")
        success, error = download_vlc()
        
        if success:
            print("✓ VLC download succeeded")
            print("✓ Checksum verification passed")
            print("✓ VLC download test PASSED")
            return True
        else:
            print(f"✗ VLC download failed: {error}")
            print("✗ VLC download test FAILED")
            return False
    except Exception as e:
        print(f"✗ VLC download test FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all stress tests"""
    print("=" * 60)
    print("VLC Download Stress Test Suite")
    print("=" * 60)
    
    tests = [
        ("Checksum Calculation", test_checksum_calculation),
        ("Checksum Mismatch Detection", test_checksum_mismatch),
        ("VLC URL Accessibility", test_vlc_urls),
        ("CHECKSUMS Dictionary Format", test_checksums_dict),
        ("VLC Download with Correct Checksum", test_download_with_correct_checksum),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except KeyboardInterrupt:
            print("\n\nTest interrupted by user")
            break
        except Exception as e:
            print(f"\n✗ Test '{test_name}' crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓✓✓ ALL TESTS PASSED ✓✓✓")
        return 0
    else:
        print(f"\n✗✗✗ {total - passed} TEST(S) FAILED ✗✗✗")
        return 1


if __name__ == "__main__":
    sys.exit(main())
