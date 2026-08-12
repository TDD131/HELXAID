"""
LibreHardwareMonitor Embedded Wrapper - Native C# DLL Integration via pythonnet

Provides 100% in-process hardware monitoring for HELXAID (CPU/GPU temps, clocks, loads, power, fans).
Reads directly from LibreHardwareMonitorLib.dll with zero external app dependencies.

Component Name: LHMEmbeddedReader
"""

import os
import sys
import math
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Cache single reader instance across ticks
_lhm_reader_instance: Optional['LHMEmbeddedReader'] = None


def get_lhm_reader_instance(dll_path: Optional[str] = None) -> 'LHMEmbeddedReader':
    """Get or create singleton instance of LHMEmbeddedReader."""
    global _lhm_reader_instance
    if _lhm_reader_instance is None:
        _lhm_reader_instance = LHMEmbeddedReader(dll_path)
    return _lhm_reader_instance


class LHMEmbeddedReader:
    """
    Native Python wrapper for LibreHardwareMonitorLib.dll via pythonnet.

    Component Name: LHMEmbeddedReader
    """
    def __init__(self, dll_path: Optional[str] = None):
        self._computer = None
        self._initialized = False
        self._dll_path = dll_path or self._resolve_dll_path()
        self._init_lhm()

    def _resolve_dll_path(self) -> str:
        """Find LibreHardwareMonitorLib.dll in tools directory or AppData."""
        appdata_tools = os.path.join(
            os.environ.get('APPDATA', ''),
            "HELXAID", "tools", "librehardwaremonitor", "LibreHardwareMonitorLib.dll"
        )
        if os.path.exists(appdata_tools):
            return appdata_tools

        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        legacy_path = os.path.join(script_dir, "assets", "LibreHardwareMonitorLib.dll")
        if os.path.exists(legacy_path):
            return legacy_path

        return appdata_tools

    def _init_lhm(self):
        """Initialize LibreHardwareMonitor Computer instance."""
        try:
            import clr
            if self._dll_path and os.path.exists(self._dll_path):
                abs_dll = os.path.abspath(self._dll_path)
                dll_dir = os.path.dirname(abs_dll)

                # Unblock Zone.Identifier stream if present (Mark of the Web)
                zone_id = abs_dll + ":Zone.Identifier"
                if os.path.exists(zone_id):
                    try: os.remove(zone_id)
                    except Exception: pass

                if dll_dir not in sys.path:
                    sys.path.append(dll_dir)
                if hasattr(os, 'add_dll_directory') and os.path.exists(dll_dir):
                    try: os.add_dll_directory(dll_dir)
                    except Exception: pass

                clr.AddReference(abs_dll)
                logger.info(f"[LHM] Loaded assembly from: {abs_dll}")
            else:
                clr.AddReference("LibreHardwareMonitorLib")

            from LibreHardwareMonitor.Hardware import Computer  # type: ignore[import-not-found, import-untyped]

            
            self._computer = Computer()
            self._computer.IsCpuEnabled = True
            self._computer.IsGpuEnabled = True
            self._computer.IsMotherboardEnabled = True
            self._computer.IsControllerEnabled = True
            self._computer.IsStorageEnabled = True
            self._computer.Open()
            self._initialized = True
            print("[LHM Engine] LibreHardwareMonitorLib opened successfully (100% Exclusive)")
        except Exception as e:
            logger.error(f"[LHM Engine] Failed to initialize LibreHardwareMonitorLib: {e}")
            self._initialized = False

    def is_available(self) -> bool:
        """Check if LHM engine is initialized and ready."""
        return self._initialized and self._computer is not None

    def read_sensors(self) -> Dict[str, Any]:
        """
        Poll all hardware sensors and return unified metric dictionary.

        Returns:
            Dict containing cpu_temp, gpu_temp, cpu_load, gpu_load, cpu_clock,
            power, gpu_power, fan_speed, sys_fan, gpu_fan, igpu_*, dgpu_*, status.
        """
        if not self.is_available():
            return {"available": False}

        metrics = {
            "available": True,
            "cpu_temp": 0.0,
            "gpu_temp": 0.0,
            # iGPU = AMD Radeon integrated graphics
            "igpu_temp": 0.0,
            "igpu_load": 0.0,
            "igpu_power": 0.0,
            # dGPU = NVIDIA / discrete
            "dgpu_temp": 0.0,
            "dgpu_load": 0.0,
            "dgpu_power": 0.0,
            "hotspot_temp": 0.0,
            "vram_temp": 0.0,
            "cpu_load": 0.0,
            "gpu_load": 0.0,
            "cpu_clock": 0.0,
            "gpu_clock": 0.0,
            "power": 0.0,
            "cpu_power": 0.0,
            "gpu_power": 0.0,
            "fan_speed": 0.0,
            "cpu_fan": 0.0,
            "gpu_fan": 0.0,
            "sys_fan": 0.0,
            "status": "lhm_embedded"
        }

        def _process_hw(hardware, metrics):
            """Process one hardware node and its sub-hardware recursively."""
            hw_type = str(hardware.HardwareType).upper()
            hw_name = str(hardware.Name).upper()

            is_cpu  = "CPU" in hw_type
            # GpuAmd  = AMD Radeon integrated (iGPU)
            # GpuNvidia = NVIDIA discrete (dGPU)
            is_igpu = "GPUAMD" in hw_type or "GPUINTEL" in hw_type
            is_dgpu = "GPUNVIDIA" in hw_type
            is_mobo = "MOTHERBOARD" in hw_type or "CONTROLLER" in hw_type or "SUPERIO" in hw_type

            # Edge-case: some boards enumerate a generic "GpuAmd" that is actually the iGPU
            # while others might show it differently. Force by name:
            if "NVIDIA" in hw_name:
                is_dgpu = True
                is_igpu = False

            for sensor in hardware.Sensors:
                try:
                    val = sensor.Value
                    if val is None:
                        continue
                    fval = float(val)
                    if math.isnan(fval):
                        continue
                except Exception:
                    continue
                stype  = str(sensor.SensorType).upper()
                sname  = str(sensor.Name).upper()

                # --- CPU ---
                if is_cpu:
                    if stype == "TEMPERATURE" and fval > 0:
                        if ("TCTL" in sname or "TDIE" in sname or "PACKAGE" in sname or "CORE MAX" in sname) and metrics["cpu_temp"] == 0:
                            metrics["cpu_temp"] = fval
                        elif "CORE" in sname and metrics["cpu_temp"] == 0:
                            metrics["cpu_temp"] = fval
                    elif stype == "LOAD":
                        if "TOTAL" in sname or "CORE MAX" in sname:
                            metrics["cpu_load"] = max(metrics["cpu_load"], fval)
                    elif stype == "CLOCK" and fval > 200:  # Ignore 100MHz bus speed, capture max core clock
                        metrics["cpu_clock"] = max(metrics["cpu_clock"], fval)
                    elif stype == "POWER" and ("PACKAGE" in sname or "CPU" in sname):
                        metrics["cpu_power"] = fval
                        metrics["power"]     = fval

                # --- iGPU (AMD Radeon integrated) ---
                elif is_igpu:
                    if stype == "TEMPERATURE":
                        if ("CORE" in sname or "GPU" in sname) and metrics["igpu_temp"] == 0:
                            metrics["igpu_temp"] = fval
                    elif stype == "LOAD" and ("CORE" in sname or "GPU" in sname):
                        metrics["igpu_load"] = max(metrics["igpu_load"], fval)
                    elif stype == "POWER":
                        metrics["igpu_power"] = fval

                # --- dGPU (NVIDIA RTX) ---
                elif is_dgpu:
                    if stype == "TEMPERATURE":
                        if "HOT SPOT" in sname or "HOTSPOT" in sname:
                            metrics["hotspot_temp"] = fval
                        elif "JUNCTION" in sname or "MEMORY" in sname:
                            metrics["vram_temp"] = fval
                        elif ("CORE" in sname or "GPU" in sname) and metrics["dgpu_temp"] == 0:
                            metrics["dgpu_temp"] = fval
                            metrics["gpu_temp"]  = fval   # keep generic alias
                    elif stype == "LOAD" and ("CORE" in sname or "3D" in sname or "GPU" in sname):
                        metrics["dgpu_load"] = max(metrics["dgpu_load"], fval)
                        metrics["gpu_load"]  = metrics["dgpu_load"]
                    elif stype == "CLOCK" and ("CORE" in sname or "GPU" in sname):
                        metrics["gpu_clock"] = fval
                    elif stype == "POWER":
                        metrics["dgpu_power"] = fval
                        metrics["gpu_power"]  = fval
                    elif stype == "FAN":
                        metrics["gpu_fan"]   = fval
                        metrics["fan_speed"] = max(metrics["fan_speed"], fval)

                # --- Motherboard / SuperIO fans ---
                elif is_mobo:
                    if stype == "FAN":
                        if "CPU" in sname:
                            metrics["cpu_fan"] = max(metrics["cpu_fan"], fval)
                        else:
                            metrics["sys_fan"] = max(metrics["sys_fan"], fval)
                        metrics["fan_speed"] = max(metrics["fan_speed"], fval)

            # Recurse into sub-hardware (e.g. CPU cores on some platforms)
            try:
                for sub in hardware.SubHardware:
                    sub.Update()
                    _process_hw(sub, metrics)
            except Exception:
                pass

        try:
            for hardware in self._computer.Hardware:
                hardware.Update()
                _process_hw(hardware, metrics)

            return metrics

        except Exception as e:
            logger.error(f"[LHM Engine] Error polling sensors: {e}")
            metrics["status"] = "error"
            return metrics

    def close(self):
        """Close computer hardware handle."""
        if self._computer:
            try:
                self._computer.Close()
            except Exception:
                pass
            self._computer = None
            self._initialized = False
