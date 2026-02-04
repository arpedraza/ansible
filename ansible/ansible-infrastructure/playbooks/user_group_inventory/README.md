# 📘 **README.md — Linux User & Group Inventory (Ansible)**

## **Overview**

This playbook set collects **local users, groups, and sudo/root privileges** from all Linux servers in the dynamic Ansible inventory.\ It creates:

- **Per-host JSON reports** – one file per Linux server
- **Consolidated JSON report** – all servers combined
- **CSV report** – Excel‑friendly version of the user/group inventory
- **Run summary CSV** – shows which hosts succeeded or failed during the inventory run

This toolkit is designed for:

- Security audits
- Sudo rights review
- Compliance reporting (ISO, SOC2, CIS)
- Forensics (“who had root access on which host”)
- Infrastructure documentation

All reports are stored inside the repository under:

```
playbooks/user_group_inventory/reports/
```

## **Folder Structure**

```
playbooks/user_group_inventory/
│
├── user_group_inventory.yml       # Collect per-host data from all Linux servers
├── export_reports.yml             # Combine data → consolidated JSON + CSV
├── run_summary.yml                # Create summary CSV (success / no report)
│
├── reports/
│   ├── per_host/                  # One JSON file per Linux host
│   ├── consolidated/              # Combined JSON (all hosts)
│   └── excel/                     # CSV reports (+ XLSX if converted manually)
│
└── roles/
    └── user_group_inventory/
        ├── defaults/
        │   └── main.yml           # Default variables
        └── tasks/
            └── main.yml           # Core collection logic
```

## **Check Which Linux Hosts Will Be Queried**

The inventory for this environment is:
``` shell
Ansible-Azure/project_windows_defender/inventory/test.yml
```

To see the **linux** group:
```shell
ansible-inventory \
  -i Ansible-Azure/project_windows_defender/inventory/test.yml \
  --graph linux
```

To list all Linux hosts:
```shell
ansible-inventory \
  -i Ansible-Azure/project_windows_defender/inventory/test.yml \
  --list | grep linux -A 50
```

To test connectivity:
```
ansible -i Ansible-Azure/project_windows_defender/inventory/test.yml \
  linux -m ping -u ansible
```
## **Collect User & Group Inventory (Per-Host JSON)**

This is the main playbook.\ It connects to all Linux servers in the dynamic group and creates one JSON file per host.

Run:
``` shell
ansible-playbook \
  -i Ansible-Azure/project_windows_defender/inventory/test.yml \
  -l linux \
  -u ansible \
  playbooks/user_group_inventory/user_group_inventory.yml
```

After successful execution, reports appear in:
``` text
playbooks/user_group_inventory/reports/per_host/
```

Example output:

```text
dbpwe-ora03-users-and-groups-30-01-2026_11.24.json
epfpwe-opa02-users-and-groups-30-01-2026_11.24.json
...
```

Each file contains:
- All local users
- All local groups
- Sudo-enabled groups
- Explicit sudoers from `/etc/sudoers`
- Which users can effectively escalate to root
## **Generate Consolidated Reports (JSON + CSV)**

This playbook reads all per-host reports and generates:
- One **consolidated JSON** containing all hosts
- One **CSV** file (Excel compatible)

Run:
```shell
ansible-playbook \
  playbooks/user_group_inventory/export_reports.yml
```

Results appear in:
```text
reports/consolidated/
reports/excel/
```

Example output:
```text
reports/consolidated/all_hosts-30-01-2026_12.40.json
reports/excel/linux_user_group_inventory-30-01-2026_12.40.csv
```

The CSV file includes:
```text
host,user,uid,groups,is_sudoer
```
## **Run Summary Report (Success / No Report)**

This playbook does _not_ connect to Linux servers.\ It inspects which hosts produced a per-host JSON and which did not.

Run:
```shell
ansible-playbook \
  playbooks/user_group_inventory/run_summary.yml
```

Produces a CSV:
```text
reports/excel/run_summary-30-01-2026_12.45.csv
```

Example:
```text
host,status,notes
dbpwe-ora03,success,
epbpwe-ste01,no_report,No per-host JSON report found; check ansible.log
sveurterpfus01-uat,no_report,No per-host JSON report found; check connection/Python
```

This is ideal for:
- Identifying unreachable servers
- Servers with Python 2.6 (too old for Ansible)
- Servers with SSH/host key problems
## **Enabling Ansible Logging (Recommended)**

To persist all Ansible output to a log file, edit:

```text
Ansible-Azure/ansible.cfg
```

Add:

[defaults]
```
log_path_ _= ./ansible.log_
_stdout_callback = yaml
stderr_callback = yaml
```

After this, every playbook run generates `ansible.log` containing:
- Task logs
- Errors
- SSH failures
- Python version issues
- Module tracebacks

Perfect for troubleshooting unreachable or failing hosts.
## **Report Locations Summary**

| Type              | Location                | Source Playbook            |
| ----------------- | ----------------------- | -------------------------- |
| Per-host JSON     | `reports/per_host/`     | `user_group_inventory.yml` |
| Consolidated JSON | `reports/consolidated/` | `export_reports.yml`       |
| CSV (all hosts)   | `reports/excel/`        | `export_reports.yml`       |
| Summary CSV       | `reports/excel/`        | `run_summary.yml`          |
## **Operational Workflow Summary**

1. **Inventory discovery** ansible-inventory -i test.yml --graph linux
2. **Connectivity test** ansible linux -m ping -u ansible
3. **Collect per-host data** ansible-playbook -i test.yml -l linux -u ansible user_group_inventory.yml
4. **Generate consolidated CSV + JSON** ansible-playbook export_reports.yml
5. **Generate run summary CSV** ansible-playbook run_summary.yml
6. **Review results**
    - `reports/per_host/`
    - `reports/consolidated/`
    - `reports/excel/`
    - `ansible.log`