from pathlib import Path
import os
import psutil
import time


class SystemMonitor:
    _network_sample = None

    @staticmethod
    def get_cpu_usage():
        return psutil.cpu_percent(interval=0.5)

    @staticmethod
    def get_memory_usage():
        memory = psutil.virtual_memory()
        return memory.percent

    @staticmethod
    def get_disk_usage():
        disk = psutil.disk_usage(Path.home().anchor or os.sep)
        return disk.percent

    @staticmethod
    def get_battery():
        battery = psutil.sensors_battery()

        if battery is None:
            return None

        return {
            "percent": battery.percent,
            "charging": battery.power_plugged
        }

    @staticmethod
    def get_network_speed():
        """Return the current aggregate network throughput in MB/s."""
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

    @staticmethod
    def get_system_info():
        return {
            "cpu": SystemMonitor.get_cpu_usage(),
            "memory": SystemMonitor.get_memory_usage(),
            "disk": SystemMonitor.get_disk_usage(),
            "battery": SystemMonitor.get_battery(),
            "network": SystemMonitor.get_network_speed(),
        }