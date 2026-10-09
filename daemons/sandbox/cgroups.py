"""
Aura Assistant - Linux cgroup v2 & Resource Enforcement Specs
Defines container security profiles and resource quotas for ephemeral runners.
"""

from dataclasses import dataclass
from typing import Dict, List, Any

@dataclass
class CgroupConstraints:
    nano_cpus: int = int(1.0 * 1e9)  # 1.0 CPU
    mem_limit: str = "512m"          # 512MB RAM
    memswap_limit: str = "512m"      # Swap disabled / matched
    pids_limit: int = 128            # Max 128 PIDs
    read_only: bool = True
    tmpfs: Dict[str, str] = None
    cap_drop: List[str] = None
    security_opt: List[str] = None
    user: str = "65534:65534"        # nobody:nogroup

    def __post_init__(self):
        if self.tmpfs is None:
            self.tmpfs = {"/tmp": "rw,size=64m"}
        if self.cap_drop is None:
            self.cap_drop = ["ALL"]
        if self.security_opt is None:
            self.security_opt = ["no-new-privileges:true"]

    def to_docker_kwargs(self) -> Dict[str, Any]:
        return {
            "nano_cpus": self.nano_cpus,
            "mem_limit": self.mem_limit,
            "memswap_limit": self.memswap_limit,
            "pids_limit": self.pids_limit,
            "read_only": self.read_only,
            "tmpfs": self.tmpfs,
            "cap_drop": self.cap_drop,
            "security_opt": self.security_opt,
            "user": self.user
        }
