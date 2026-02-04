#!/usr/bin/env python3
import json
import os
import sys
import time
import subprocess
from typing import Dict, Any, List, Tuple, Optional

# -------------------------
# Tuning knobs
# -------------------------
CACHE_FILE = os.path.expanduser("~/.azure_inventory_cache.json")
CACHE_TTL_SECONDS = 300          # 5 minutes
GRAPH_PAGE_SIZE = 1000
AZ_TIMEOUT_SECONDS = 30          # hard cap per az call

# -------------------------
# Helpers
# -------------------------
def graph_api_get(url: str, timeout: int = AZ_TIMEOUT_SECONDS) -> Optional[Dict[str, Any]]:
    """
    Call Microsoft Graph via az rest.
    """
    try:
        r = az(
            [
                "rest",
                "--method", "GET",
                "--url", url,
                "--headers", "ConsistencyLevel=eventual"
            ],
            timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return None

    if r.returncode != 0 or not r.stdout.strip():
        return None

    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None

def get_mde_windows_machine_keys() -> set[str]:
    """
    Returns a set of keys representing Defender-onboarded Windows machines.
    Keys include azureVmId (preferred) and short hostname (fallback).
    Presence in this set == onboarded.
    """
    url = "https://graph.microsoft.com/v1.0/security/machines?$top=1000"
    keys: set[str] = set()

    while url:
        payload = graph_api_get(url)
        if not payload:
            break

        for m in payload.get("value", []):
            if m.get("osPlatform") != "Windows":
                continue

            if m.get("azureVmId"):
                keys.add(m["azureVmId"].lower())

            if m.get("computerDnsName"):
                keys.add(m["computerDnsName"].split(".")[0].lower())

        url = payload.get("@odata.nextLink")

    return keys

def az(cmd: List[str], timeout: int = AZ_TIMEOUT_SECONDS) -> subprocess.CompletedProcess:
    """
    Run Azure CLI command. Never hangs: bounded by timeout.
    """
    return subprocess.run(
        ["az"] + cmd,
        capture_output=True,
        text=True,
        timeout=timeout
    )

def empty_inventory() -> Dict[str, Any]:
    return {"_meta": {"hostvars": {}}, "all": {"hosts": []}, "linux": {"hosts": []}, "windows": {"hosts": []}, "network_appliances": {"hosts": []}, "windows_mde_onboarded": {"hosts": []}, "windows_mde_not_onboarded": {"hosts": []}}

def load_cache_if_fresh() -> Optional[str]:
    try:
        if os.path.exists(CACHE_FILE) and (time.time() - os.path.getmtime(CACHE_FILE) < CACHE_TTL_SECONDS):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return f.read()
    except Exception:
        pass
    return None

def save_cache(payload: Dict[str, Any]) -> None:
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f)
    except Exception:
        # Cache failure should never break inventory output
        pass

def graph_query_all(query: str, page_size: int = GRAPH_PAGE_SIZE) -> List[Dict[str, Any]]:
    """
    Fetch all results for an Azure Resource Graph query using skipToken pagination.
    Returns [] if anything goes wrong (inventory will degrade gracefully).
    """
    results: List[Dict[str, Any]] = []
    skip_token: Optional[str] = None

    while True:
        cmd = ["graph", "query", "-q", query, "--first", str(page_size), "-o", "json"]
        if skip_token:
            cmd += ["--skip-token", skip_token]

        try:
            r = az(cmd, timeout=AZ_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            return []

        if r.returncode != 0 or not r.stdout.strip():
            return []

        try:
            payload = json.loads(r.stdout)
        except json.JSONDecodeError:
            return []

        data = payload.get("data") or []
        results.extend(data)

        # Azure CLI typically returns skipToken when more pages exist
        skip_token = payload.get("skipToken") or payload.get("skip_token") or None
        if not skip_token:
            break

    return results

APPLIANCE_PUBLISHERS = {
    "citrix",
    "barracudanetworks",
    "f5-networks",
    "paloaltonetworks",
    "fortinet",
    "sophos",
    "checkpoint",
    "cisco"
}

# -------------------------
# Main
# -------------------------
def main() -> None:
    # 1) Serve cache immediately if fresh
    cached = load_cache_if_fresh()
    if cached is not None:
        print(cached)
        return

    # 2) Two bulk ARG queries: VMs + NICs (fastest approach)
    vm_query = """
Resources
| where type == 'microsoft.compute/virtualmachines'
| project
    name,
    resourceGroup,
    location,
    osType = tostring(properties.storageProfile.osDisk.osType),
    publisher = tostring(properties.storageProfile.imageReference.publisher),
    offer     = tostring(properties.storageProfile.imageReference.offer),
    sku       = tostring(properties.storageProfile.imageReference.sku),
    nicId  = tostring(properties.networkProfile.networkInterfaces[0].id)
"""

    nic_query = """
Resources
| where type == 'microsoft.network/networkinterfaces'
| project
    id,
    privateIp = tostring(properties.ipConfigurations[0].properties.privateIPAddress)
"""

    vms = graph_query_all(vm_query)
    nics = graph_query_all(nic_query)
    mde_windows_keys = get_mde_windows_machine_keys()

    # If Azure CLI / graph fails, return empty inventory (don’t break Ansible)
    if not vms:
        inv = empty_inventory()
        save_cache(inv)
        print(json.dumps(inv, indent=2))
        return

    # 3) Build NIC -> IP map locally (O(1) lookups)
    nic_ip_map: Dict[str, Optional[str]] = {}
    for nic in nics:
        nic_id = nic.get("id")
        if nic_id:
            nic_ip_map[nic_id] = (nic.get("privateIp") or "").strip() or None

    # 4) Build inventory
    inventory = empty_inventory()

    for vm in vms:
        name = (vm.get("name") or "").strip()
        if not name:
            continue

        nic_id = vm.get("nicId")
        ip = nic_ip_map.get(nic_id)

        inventory["all"]["hosts"].append(name)
        inventory["_meta"]["hostvars"][name] = {
            "ansible_host": ip,          # Connection target (IP)
            "private_ip": ip,            # Metadata
            "resource_group": vm.get("resourceGroup"),
            "location": vm.get("location"),
            "os_type": vm.get("osType"),
            "nic_id": nic_id
        }

        publisher = (vm["publisher"] or "").lower()
        is_appliance = any(p in publisher for p in APPLIANCE_PUBLISHERS)

        if vm.get("osType") == "Linux" and not is_appliance:
            inventory["linux"]["hosts"].append(name)

        elif vm.get("osType") == "Linux" and is_appliance:
            inventory["network_appliances"]["hosts"].append(name)

        elif vm.get("osType") == "Windows":
            inventory["windows"]["hosts"].append(name)

            vm_id_key = (vm.get("id") or "").lower()
            name_key = name.lower()

            is_onboarded = (
                vm_id_key in mde_windows_keys
                or name_key in mde_windows_keys
            )

            inventory["_meta"]["hostvars"][name]["mde_onboarded"] = is_onboarded

            if is_onboarded:
                inventory["windows_mde_onboarded"]["hosts"].append(name)
            else:
                inventory["windows_mde_not_onboarded"]["hosts"].append(name)
        
        else:
            inventory["windows"]["hosts"].append(name)

    # 5) Cache + output
    save_cache(inventory)
    print(json.dumps(inventory, indent=2))

if __name__ == "__main__":
    main()

