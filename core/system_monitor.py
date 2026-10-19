"""Cross-platform system monitor for NEXUS."""

from __future__ import annotations

import os
import time
from pathlib import Path

import psutil


class SystemMonitor:
    _network_sample = None

    @staticmethod
    def get_cpu_usage():
        # Non-blocking quick sample; first call may return 0.0 on some platforms
        return psutil.cpu_percent(interval=0.3)

    @staticmethod
    def get_memory_usage():
        memory = psutil.virtual_memory()
        return float(memory.percent)

    @staticmethod
    def get_disk_usage():
        """Return disk usage percent for the appropriate volume on any OS."""
        try:
            if os.name == "nt":
                disk = psutil.disk_usage("C:\\")
            else:
                # On Linux/macOS use the root filesystem or home partition
                home = str(Path.home())
                try:
                    disk = psutil.disk_usage(home)
                except Exception:
                    disk = psutil.disk_usage("/")
            return float(disk.percent)
        except Exception:
            # Fallback: average of all partitions
            try:
                partitions = psutil.disk_partitions(all=False)
                usages = []
                for p in partitions:
                    try:
                        usages.append(psutil.disk_usage(p.mountpoint).percent)
                    except Exception:
                        continue
                return float(sum(usages) / len(usages)) if usages else 0.0
            except Exception:
                return 0.0

    @staticmethod
    def get_battery():
        try:
            battery = psutil.sensors_battery()
        except Exception:
            return None
        if battery is None:
            return None
        try:
            return {
                "percent": float(battery.percent),
                "charging": bool(battery.power_plugged),
            }
        except Exception:
            return None

    @staticmethod
    def get_network_speed():
        """Return the current aggregate network throughput in MB/s."""
        try:
            counters = psutil.net_io_counters()
            now = time.monotonic()
            previous = SystemMonitor._network_sample
            SystemMonitor._network_sample = (now, counters.bytes_sent + counters.bytes_recv)
            if previous is None:
                return 0.0
            elapsed = now - previous[0]
            if elapsed <= 0:
                return 0.0
            return max(0.0, (SystemMonitor._network_sample[1] - previous[1]) / elapsed / (1024 ** 2))
        except Exception:
            return 0.0

    @staticmethod
    def get_system_info():
        return {
            "cpu": SystemMonitor.get_cpu_usage(),
            "memory": SystemMonitor.get_memory_usage(),
            "disk": SystemMonitor.get_disk_usage(),
            "battery": SystemMonitor.get_battery(),
            "network": SystemMonitor.get_network_speed(),
        }

    @staticmethod
    def get_detailed_info():
        """Return extended system info for diagnostics."""
        info = SystemMonitor.get_system_info()
        try:
            info["cpu_count"] = psutil.cpu_count(logical=True)
            info["cpu_physical"] = psutil.cpu_count(logical=False)
        except Exception:
            pass
        try:
            vm = psutil.virtual_memory()
            info["memory_total_gb"] = round(vm.total / (1024**3), 2)
            info["memory_available_gb"] = round(vm.available / (1024**3), 2)
        except Exception:
            pass
        try:
            info["uptime_seconds"] = time.time() - psutil.boot_time()
        except Exception:
            pass
        return info
