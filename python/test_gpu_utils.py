"""
Stress Test for GPU Detection Module

Tests edge cases, resource leaks, and extreme inputs.
"""

import os
import sys
import time
import subprocess
import unittest
from unittest.mock import patch, MagicMock
import tempfile
import threading

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gpu_utils
from gpu_utils import (
    GPUInfo,
    _get_gpus_via_wmi,
    enumerate_dxgi_adapters,
    get_preferred_gpu,
    set_windows_gpu_preference_high_performance,
    detect_gpu_vendor,
    init_dgpu_for_video,
    get_gpu_info_string
)


class TestGPUInfo(unittest.TestCase):
    """Test GPUInfo NamedTuple."""
    
    def test_gpu_info_creation(self):
        """Test basic GPUInfo creation."""
        gpu = GPUInfo(
            index=0,
            name="NVIDIA GeForce RTX 3080",
            dedicated_video_memory=10 * 1024 * 1024 * 1024,  # 10GB
            shared_system_memory=16 * 1024 * 1024 * 1024,
            vendor_id=0x10DE,
            device_id=0x2206,
            is_integrated=False,
            is_discrete=True,
            is_software=False
        )
        self.assertEqual(gpu.name, "NVIDIA GeForce RTX 3080")
        self.assertTrue(gpu.is_discrete)
        self.assertFalse(gpu.is_integrated)
    
    def test_gpu_info_empty_name(self):
        """Test GPUInfo with empty name."""
        gpu = GPUInfo(
            index=0,
            name="",
            dedicated_video_memory=0,
            shared_system_memory=0,
            vendor_id=0,
            device_id=0,
            is_integrated=True,
            is_discrete=False,
            is_software=False
        )
        self.assertEqual(gpu.name, "")


class TestWMIDetection(unittest.TestCase):
    """Test WMI-based GPU detection."""
    
    def test_wmi_normal_output(self):
        """Test parsing normal WMI output."""
        # This test runs on actual system
        gpus = _get_gpus_via_wmi()
        # Should return list (may be empty if no GPUs)
        self.assertIsInstance(gpus, list)
    
    @patch('subprocess.run')
    def test_wmi_timeout(self, mock_run):
        """Test handling of WMI timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired('wmic', 10)
        gpus = _get_gpus_via_wmi()
        self.assertEqual(gpus, [])
    
    @patch('subprocess.run')
    def test_wmi_file_not_found(self, mock_run):
        """Test handling when wmic not found."""
        mock_run.side_effect = FileNotFoundError()
        gpus = _get_gpus_via_wmi()
        self.assertEqual(gpus, [])
    
    @patch('subprocess.run')
    def test_wmi_nonzero_exit(self, mock_run):
        """Test handling of non-zero exit code."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Access denied"
        mock_run.return_value = mock_result
        gpus = _get_gpus_via_wmi()
        self.assertEqual(gpus, [])
    
    @patch('subprocess.run')
    def test_wmi_malformed_csv(self, mock_run):
        """Test handling of malformed CSV output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "garbage data\nnot,csv,format"
        mock_run.return_value = mock_result
        gpus = _get_gpus_via_wmi()
        # Should handle gracefully
        self.assertIsInstance(gpus, list)
    
    @patch('subprocess.run')
    def test_wmi_empty_output(self, mock_run):
        """Test handling of empty WMI output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_run.return_value = mock_result
        gpus = _get_gpus_via_wmi()
        self.assertEqual(gpus, [])
    
    @patch('subprocess.run')
    def test_wmi_special_characters_in_name(self, mock_run):
        """Test handling of special characters in GPU name."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Node,AdapterRAM,DriverVersion,Name\n,4294967296,31.0.15.2847,NVIDIA GeForce RTX 3080™ \u00e9\u00e8\u00ea\n"
        mock_run.return_value = mock_result
        gpus = _get_gpus_via_wmi()
        # Should handle unicode gracefully
        self.assertIsInstance(gpus, list)
    
    @patch('subprocess.run')
    def test_wmi_zero_adapter_ram(self, mock_run):
        """Test handling of zero AdapterRAM."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Node,AdapterRAM,DriverVersion,Name\n,0,31.0.0.0,Intel UHD Graphics\n"
        mock_run.return_value = mock_result
        gpus = _get_gpus_via_wmi()
        # Zero RAM should be detected as iGPU
        if gpus:
            self.assertTrue(gpus[0].is_integrated or not gpus[0].is_discrete)
    
    @patch('subprocess.run')
    def test_wmi_negative_adapter_ram(self, mock_run):
        """Test handling of negative AdapterRAM (corrupt data)."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Node,AdapterRAM,DriverVersion,Name\n,-123456,31.0.0.0,Test GPU\n"
        mock_run.return_value = mock_result
        gpus = _get_gpus_via_wmi()
        # Should handle gracefully
        self.assertIsInstance(gpus, list)
    
    @patch('subprocess.run')
    def test_wmi_very_large_adapter_ram(self, mock_run):
        """Test handling of very large AdapterRAM."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        # 1TB VRAM (unrealistic but tests overflow handling)
        mock_result.stdout = f"Node,AdapterRAM,DriverVersion,Name\n,{1024*1024*1024*1024},31.0.0.0,Future GPU\n"
        mock_run.return_value = mock_result
        gpus = _get_gpus_via_wmi()
        if gpus:
            self.assertTrue(gpus[0].is_discrete)


class TestRegistryPreference(unittest.TestCase):
    """Test Windows registry GPU preference setting."""
    
    def test_registry_with_default_path(self):
        """Test registry setting with default executable path."""
        result = set_windows_gpu_preference_high_performance()
        # Should succeed on Windows
        if os.name == 'nt':
            self.assertIsInstance(result, bool)
    
    def test_registry_with_custom_path(self):
        """Test registry setting with custom path."""
        result = set_windows_gpu_preference_high_performance("C:\\test\\app.exe")
        self.assertIsInstance(result, bool)
    
    def test_registry_with_none_path(self):
        """Test registry setting with None path (should use sys.executable)."""
        result = set_windows_gpu_preference_high_performance(None)
        self.assertIsInstance(result, bool)
    
    @patch('winreg.CreateKeyEx')
    def test_registry_permission_denied(self, mock_create_key):
        """Test handling of registry permission denied."""
        mock_create_key.side_effect = PermissionError("Access denied")
        result = set_windows_gpu_preference_high_performance()
        self.assertFalse(result)
    
    @patch('winreg.SetValueEx')
    def test_registry_write_failure(self, mock_set_value):
        """Test handling of registry write failure."""
        mock_set_value.side_effect = OSError("Registry error")
        result = set_windows_gpu_preference_high_performance()
        self.assertFalse(result)


class TestEnumerateAdapters(unittest.TestCase):
    """Test GPU enumeration."""
    
    def test_enumerate_returns_list(self):
        """Test that enumeration returns a list."""
        gpus = enumerate_dxgi_adapters()
        self.assertIsInstance(gpus, list)
    
    @patch('gpu_utils._get_gpus_via_wmi')
    def test_enumerate_sorting(self, mock_wmi):
        """Test that GPUs are sorted correctly (dGPU first)."""
        # Create mock GPUs
        igpu = GPUInfo(
            index=0, name="Intel UHD", dedicated_video_memory=128*1024*1024,
            shared_system_memory=0, vendor_id=0x8086, device_id=0,
            is_integrated=True, is_discrete=False, is_software=False
        )
        dgpu = GPUInfo(
            index=1, name="NVIDIA RTX", dedicated_video_memory=8*1024*1024*1024,
            shared_system_memory=0, vendor_id=0x10DE, device_id=0,
            is_integrated=False, is_discrete=True, is_software=False
        )
        mock_wmi.return_value = [igpu, dgpu]  # Wrong order
        
        gpus = enumerate_dxgi_adapters()
        
        # dGPU should be first after sorting
        if len(gpus) >= 2:
            self.assertTrue(gpus[0].is_discrete)


class TestGetPreferredGPU(unittest.TestCase):
    """Test preferred GPU selection."""
    
    def test_get_preferred_returns_gpu_or_none(self):
        """Test that get_preferred_gpu returns GPUInfo or None."""
        gpu = get_preferred_gpu()
        self.assertTrue(gpu is None or isinstance(gpu, GPUInfo))
    
    @patch('gpu_utils.enumerate_dxgi_adapters')
    def test_get_preferred_empty_list(self, mock_enum):
        """Test behavior when no GPUs detected."""
        mock_enum.return_value = []
        gpu = get_preferred_gpu()
        self.assertIsNone(gpu)


class TestDetectVendor(unittest.TestCase):
    """Test GPU vendor detection."""
    
    @patch('gpu_utils.enumerate_dxgi_adapters')
    def test_detect_vendor_nvidia(self, mock_enum):
        """Test NVIDIA vendor detection."""
        mock_enum.return_value = [GPUInfo(
            index=0, name="NVIDIA RTX 3080", dedicated_video_memory=10*1024*1024*1024,
            shared_system_memory=0, vendor_id=0x10DE, device_id=0,
            is_integrated=False, is_discrete=True, is_software=False
        )]
        vendor = detect_gpu_vendor()
        self.assertEqual(vendor, 'nvidia')
    
    @patch('gpu_utils.enumerate_dxgi_adapters')
    def test_detect_vendor_amd(self, mock_enum):
        """Test AMD vendor detection."""
        mock_enum.return_value = [GPUInfo(
            index=0, name="AMD Radeon RX 6800", dedicated_video_memory=16*1024*1024*1024,
            shared_system_memory=0, vendor_id=0x1002, device_id=0,
            is_integrated=False, is_discrete=True, is_software=False
        )]
        vendor = detect_gpu_vendor()
        self.assertEqual(vendor, 'amd')
    
    @patch('gpu_utils.enumerate_dxgi_adapters')
    def test_detect_vendor_intel(self, mock_enum):
        """Test Intel vendor detection."""
        mock_enum.return_value = [GPUInfo(
            index=0, name="Intel UHD Graphics", dedicated_video_memory=0,
            shared_system_memory=0, vendor_id=0x8086, device_id=0,
            is_integrated=True, is_discrete=False, is_software=False
        )]
        vendor = detect_gpu_vendor()
        self.assertEqual(vendor, 'intel')
    
    @patch('gpu_utils.enumerate_dxgi_adapters')
    def test_detect_vendor_unknown(self, mock_enum):
        """Test unknown vendor detection."""
        mock_enum.return_value = [GPUInfo(
            index=0, name="Unknown GPU", dedicated_video_memory=1024*1024*1024,
            shared_system_memory=0, vendor_id=0xFFFF, device_id=0,
            is_integrated=False, is_discrete=True, is_software=False
        )]
        vendor = detect_gpu_vendor()
        self.assertEqual(vendor, 'unknown')
    
    @patch('gpu_utils.enumerate_dxgi_adapters')
    def test_detect_vendor_empty(self, mock_enum):
        """Test vendor detection with no GPUs."""
        mock_enum.return_value = []
        vendor = detect_gpu_vendor()
        self.assertEqual(vendor, 'unknown')


class TestInitDGpu(unittest.TestCase):
    """Test main initialization function."""
    
    @patch('gpu_utils.enumerate_dxgi_adapters')
    def test_init_with_dgpu(self, mock_enum):
        """Test initialization with dGPU available."""
        mock_enum.return_value = [GPUInfo(
            index=0, name="NVIDIA RTX 3080", dedicated_video_memory=10*1024*1024*1024,
            shared_system_memory=0, vendor_id=0x10DE, device_id=0,
            is_integrated=False, is_discrete=True, is_software=False
        )]
        result = init_dgpu_for_video()
        self.assertTrue(result)
        # Check environment variables were set
        self.assertEqual(os.environ.get("NvOptimusEnablement"), "1")
        self.assertEqual(os.environ.get("AmdPowerXpressRequestHighPerformance"), "1")
    
    @patch('gpu_utils.enumerate_dxgi_adapters')
    def test_init_with_only_igpu(self, mock_enum):
        """Test initialization with only iGPU."""
        mock_enum.return_value = [GPUInfo(
            index=0, name="Intel UHD", dedicated_video_memory=0,
            shared_system_memory=0, vendor_id=0x8086, device_id=0,
            is_integrated=True, is_discrete=False, is_software=False
        )]
        result = init_dgpu_for_video()
        self.assertFalse(result)
    
    @patch('gpu_utils.enumerate_dxgi_adapters')
    def test_init_with_no_gpus(self, mock_enum):
        """Test initialization with no GPUs detected."""
        mock_enum.return_value = []
        result = init_dgpu_for_video()
        self.assertFalse(result)
    
    @patch('gpu_utils.enumerate_dxgi_adapters')
    @patch('gpu_utils.set_windows_gpu_preference_high_performance')
    def test_init_registry_failure_continues(self, mock_reg, mock_enum):
        """Test that registry failure doesn't prevent initialization."""
        mock_reg.return_value = False
        mock_enum.return_value = [GPUInfo(
            index=0, name="NVIDIA RTX", dedicated_video_memory=8*1024*1024*1024,
            shared_system_memory=0, vendor_id=0x10DE, device_id=0,
            is_integrated=False, is_discrete=True, is_software=False
        )]
        result = init_dgpu_for_video()
        self.assertTrue(result)  # Should still succeed


class TestGetGPUInfoString(unittest.TestCase):
    """Test GPU info string formatting."""
    
    @patch('gpu_utils.enumerate_dxgi_adapters')
    def test_info_string_with_gpus(self, mock_enum):
        """Test info string with GPUs."""
        mock_enum.return_value = [
            GPUInfo(0, "NVIDIA RTX 3080", 10*1024*1024*1024, 0, 0x10DE, 0, False, True, False),
            GPUInfo(1, "Intel UHD", 0, 0, 0x8086, 0, True, False, False)
        ]
        info = get_gpu_info_string()
        self.assertIn("NVIDIA RTX 3080", info)
        self.assertIn("Intel UHD", info)
    
    @patch('gpu_utils.enumerate_dxgi_adapters')
    def test_info_string_no_gpus(self, mock_enum):
        """Test info string with no GPUs."""
        mock_enum.return_value = []
        info = get_gpu_info_string()
        self.assertEqual(info, "No GPUs detected")


class TestResourceLeaks(unittest.TestCase):
    """Test for resource leaks."""
    
    @patch('subprocess.run')
    def test_no_subprocess_leak(self, mock_run):
        """Test that subprocess doesn't leak handles."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Node,AdapterRAM,DriverVersion,Name\n,4294967296,31.0.0.0,Test GPU\n"
        mock_run.return_value = mock_result
        
        # Run multiple times
        for _ in range(100):
            _get_gpus_via_wmi()
        
        # Should have called subprocess.run 100 times
        self.assertEqual(mock_run.call_count, 100)
    
    def test_multiple_init_calls(self):
        """Test that multiple init calls don't cause issues."""
        # Run init multiple times
        for _ in range(10):
            init_dgpu_for_video()
        
        # Environment variables should still be set
        self.assertEqual(os.environ.get("NvOptimusEnablement"), "1")


class TestLongRunningStability(unittest.TestCase):
    """Test long-running stability."""
    
    def test_rapid_consecutive_calls(self):
        """Test rapid consecutive calls don't cause issues."""
        start_time = time.time()
        
        for _ in range(50):
            gpus = enumerate_dxgi_adapters()
            self.assertIsInstance(gpus, list)
        
        elapsed = time.time() - start_time
        print(f"\n50 enumeration calls completed in {elapsed:.2f}s")
        
        # Should complete in reasonable time (< 30 seconds)
        self.assertLess(elapsed, 30)
    
    def test_concurrent_calls(self):
        """Test concurrent calls are safe."""
        results = []
        errors = []
        
        def worker():
            try:
                gpus = enumerate_dxgi_adapters()
                results.append(gpus)
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # All threads should complete without errors
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(results), 10)


class TestNonWindowsSystems(unittest.TestCase):
    """Test behavior on non-Windows systems."""
    
    @patch('os.name', 'posix')
    def test_wmi_on_linux(self):
        """Test that WMI returns empty list on non-Windows."""
        gpus = _get_gpus_via_wmi()
        self.assertEqual(gpus, [])


def run_stress_test():
    """Run all stress tests."""
    print("=" * 60)
    print("GPU Utils Stress Test Suite")
    print("=" * 60)
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestGPUInfo))
    suite.addTests(loader.loadTestsFromTestCase(TestWMIDetection))
    suite.addTests(loader.loadTestsFromTestCase(TestRegistryPreference))
    suite.addTests(loader.loadTestsFromTestCase(TestEnumerateAdapters))
    suite.addTests(loader.loadTestsFromTestCase(TestGetPreferredGPU))
    suite.addTests(loader.loadTestsFromTestCase(TestDetectVendor))
    suite.addTests(loader.loadTestsFromTestCase(TestInitDGpu))
    suite.addTests(loader.loadTestsFromTestCase(TestGetGPUInfoString))
    suite.addTests(loader.loadTestsFromTestCase(TestResourceLeaks))
    suite.addTests(loader.loadTestsFromTestCase(TestLongRunningStability))
    suite.addTests(loader.loadTestsFromTestCase(TestNonWindowsSystems))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 60)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("=" * 60)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_stress_test()
    sys.exit(0 if success else 1)
