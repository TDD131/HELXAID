"""Debug script: test all tiers of drive health detection."""
import ctypes
import struct
import os
import sys
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "python"))

print("=" * 60)
print("TIER 1: NVMe IOCTL (non-admin)")
print("=" * 60)

k32 = ctypes.windll.kernel32

for idx in range(4):
    path = f"\\\\.\\PhysicalDrive{idx}"
    h = k32.CreateFileW(path, 0, 0x01 | 0x02, None, 3, 0, None)
    mode = "zero"
    if h in (-1, 0, 0xFFFFFFFFFFFFFFFF):
        h = k32.CreateFileW(path, 0x80000000, 0x01 | 0x02, None, 3, 0, None)
        mode = "read"
    if h in (-1, 0, 0xFFFFFFFFFFFFFFFF):
        print(f"  Drive {idx}: CANNOT OPEN (err={ctypes.GetLastError()})")
        continue
    print(f"  Drive {idx}: opened ({mode} mode)")

    in_buf = (ctypes.c_ubyte * 48)()
    out_buf = (ctypes.c_ubyte * 560)()
    ret = ctypes.c_ulong()
    struct.pack_into("<II", in_buf, 0, 49, 0)
    struct.pack_into("<IIIIIIIIII", in_buf, 8, 3, 2, 0x02, 0, 40, 512, 0, 0, 0, 0)
    ok = k32.DeviceIoControl(
        h, 0x002D1400,
        ctypes.byref(in_buf), 48,
        ctypes.byref(out_buf), 560,
        ctypes.byref(ret), None,
    )
    err = ctypes.GetLastError()
    if ok and ret.value >= 54:
        raw = bytes(out_buf[: ret.value])
        proto_offset = struct.unpack_from('<I', raw, 24)[0] if len(raw) >= 28 else 40
        data_offset = 8 + proto_offset if (8 + proto_offset + 6 <= len(raw)) else 48
        if data_offset + 6 <= len(raw):
            crit_warn = int(raw[data_offset])
            tk = int.from_bytes(raw[data_offset + 1:data_offset + 3], "little")
            temp = max(0, tk - 273) if 200 < tk < 400 else 0
            spare = int(raw[data_offset + 3])
            wear = int(raw[data_offset + 5])
            media_errs = 0
            if data_offset + 168 <= len(raw):
                media_errs = int.from_bytes(raw[data_offset + 160:data_offset + 168], "little")
            print(f"    NVMe OK: wear={wear}%, temp={temp}C, spare={spare}%, crit_warn={crit_warn}, media_errors={media_errs}")
    else:
        print(f"    NVMe FAILED: ok={ok}, bytes={ret.value}, err={err}")

    k32.CloseHandle(h)

print()
print("=" * 60)
print("TIER 2: ATA SMART via WMI (MSStorageDriver_FailurePredictData)")
print("=" * 60)

try:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    loc = win32com.client.Dispatch("WbemScripting.SWbemLocator")

    # Get PNPDeviceID -> drive index mapping
    svc_cimv2 = loc.ConnectServer(".", "root\\cimv2")
    dd_rows = list(svc_cimv2.ExecQuery("SELECT DeviceID, PNPDeviceID FROM Win32_DiskDrive"))
    pnp_to_idx = {}
    for dd in dd_rows:
        devid = str(getattr(dd, "DeviceID", ""))
        pnp = str(getattr(dd, "PNPDeviceID", "")).lower().rstrip("\\")
        m = re.search(r'physicaldrive(\d+)', devid.lower())
        if m and pnp:
            pnp_to_idx[pnp] = int(m.group(1))
            print(f"  Win32_DiskDrive: {devid} -> PNP={pnp}")

    try:
        svc = loc.ConnectServer(".", "root\\wmi")
        rows = list(svc.ExecQuery(
            "SELECT InstanceName, VendorSpecific FROM MSStorageDriver_FailurePredictData"
        ))
        print(f"  Found {len(rows)} FailurePredictData instance(s)")
        for item in rows:
            iname = str(getattr(item, "InstanceName", ""))
            iname_lower = iname.lower().rstrip("_ \t")
            vs = getattr(item, "VendorSpecific", None)
            vs_len = len(list(vs)) if vs else 0
            print(f"  Instance: {iname[:100]}")
            print(f"    (VendorSpecific len={vs_len})")

            # Match to drive index
            didx = None
            for pnp, idx in pnp_to_idx.items():
                if pnp in iname_lower or iname_lower.startswith(pnp):
                    didx = idx
                    break
            print(f"    Matched drive index: {didx}")

            if vs and vs_len >= 362:
                data = list(vs)
                attrs = {}
                for i in range(30):
                    off = 2 + i * 12
                    aid = data[off]
                    if aid == 0:
                        continue
                    raw_b = bytes(data[off + 5 : off + 12]).ljust(8, b"\x00")
                    attrs[aid] = struct.unpack_from("<Q", raw_b)[0] & 0xFFFFFFFF
                temp = int(attrs.get(194, attrs.get(190, 0)) & 0xFF)
                realloc = int(attrs.get(5, 0))
                pending = int(attrs.get(197, 0))
                uncorr = int(attrs.get(198, 0))
                print(f"    Temp={temp}C  Reallocated={realloc}  Pending={pending}  Uncorrectable={uncorr}")
                print(f"    All attr IDs: {sorted(attrs.keys())}")
            else:
                print(f"    (not enough data)")
    except Exception as wmi_err:
        print(f"  MSStorageDriver_FailurePredictData: Not supported or no ATA drives ({wmi_err})")
    pythoncom.CoUninitialize()
except Exception as e:
    print(f"  ERROR: {e}")
    import traceback; traceback.print_exc()

print()
print("=" * 60)
print("TIER 3: Direct WMI root\\microsoft\\windows\\storage")
print("=" * 60)

try:
    from utils.drive_utils import _read_storage_wmi_local
    msft_counters = _read_storage_wmi_local()
    if msft_counters:
        for didx, data in msft_counters.items():
            print(f"  Drive {didx}: Wear={data.get('wear')}% Temp={data.get('temp')}C Errors={data.get('read_errors')}")
    else:
        print("  MSFT_StorageReliabilityCounter: No data or non-admin")
except Exception as e:
    print(f"  ERROR: {e}")

print()
print("=" * 60)
print("TIER 4: CrystalDiskInfo Direct Integration")
print("=" * 60)

try:
    from integrations.crystal_disk_info import get_crystal_disk_info_path, query_crystal_disk_info
    cdi_path = get_crystal_disk_info_path()
    print(f"  CrystalDiskInfo Path: {cdi_path}")
    if cdi_path:
        cdi_disks = query_crystal_disk_info()
        print(f"  Disks detected via CDI: {len(cdi_disks)}")
        for didx, dinfo in cdi_disks.items():
            print(f"    Drive {didx}: model='{dinfo.get('model')}', temp={dinfo.get('temp')}C, health={dinfo.get('health_pct')}%, status={dinfo.get('status')}, type={dinfo.get('media_type')}")
    else:
        print("  CrystalDiskInfo executable not found.")
except Exception as e:
    print(f"  ERROR: {e}")

print()
print("=" * 60)
print("TIER 5: Service IPC (get_drive_health)")
print("=" * 60)

try:
    from integrations.cpu_controller import send_service_command
    resp = send_service_command({"action": "get_drive_health"})
    if resp and resp.get("status") == "success":
        print("  Service Debug Log:")
        for log_line in resp.get("debug", []):
            print(f"    {log_line}")
        for dev_id, c in resp.get("counters", {}).items():
            wear = int(c.get("Wear", 0) or 0)
            temp = int(c.get("Temperature", 0) or 0)
            errs = int(c.get("ReadErrors", 0) or 0)
            model = c.get("Model", "?")
            health_pct = c.get("HealthPct", 100 - wear)
            status = c.get("Status", "HEALTHY")
            source = c.get("Source", "service")
            print(f"  Drive {dev_id}: model={model}, health={health_pct}% ({status}), wear={wear}%, temp={temp}C, errors={errs}, source={source}")
    else:
        print(f"  Service returned: {resp}")
except Exception as e:
    print(f"  ERROR: {e}")

print()
print("=" * 60)
print("UNIFIED: query_drive_health()")
print("=" * 60)

try:
    from utils.drive_utils import query_drive_health
    results = query_drive_health()
    if results:
        for idx, h in sorted(results.items()):
            print(f"  Drive {idx}: model='{h.get('model', '')}' type={h.get('type', '')} health={h['health_pct']}% ({h.get('status', '')}) temp={h['temp']}C wear={h['wear']}% avail_spare={h.get('avail_spare', 0)}% source={h['source']}")
    else:
        print("  No results returned")
except Exception as e:
    print(f"  ERROR: {e}")
    import traceback; traceback.print_exc()

print()
print("DONE")
