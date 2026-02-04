# Linux Admin Lifecycle Management (Ansible)

This repository provides a **safe, auditable, and idempotent** way to manage Linux administrator accounts across heterogeneous Linux environments (Debian-based, Red Hat–based, Oracle Linux).

It implements a **full lifecycle model** for admin users:

- Onboarding   
- Access revocation
- Offboarding with home archiving
- Final decommission

The system is designed to:

- Avoid manual server work
- Prevent accidental data loss
- Be reversible where technically possible
- Scale safely across many servers

---

## Operation Manual

### Source of truth

All admin users are defined in:

```
group_vars/all/admins.yml
```

Each user has a **`state`**, which controls everything.

### Supported states

| State      | Meaning                                     |
| ---------- | ------------------------------------------- |
| `present`  | User is active, admin access granted        |
| `revoked`  | User fully blocked (no login, no sudo)      |
| `offboard` | User blocked + home archived + home removed |
| `decom`    | User deleted + archive preserved            |
## 🔁 Lifecycle Behavior (What actually happens)

### `present` (Onboard / Active)

- User exists
- Member of admin group
- SSH keys installed
- Password set **only on first creation**
- Forced password change on first login
- Home directory present

**User can:**
- SSH
- Use sudo
- Work normally
### `revoked` (Immediate access removal)

- SSH keys removed    
- Removed from admin group
- Password locked
- Account expired
- Login shell set to `nologin`

**User can:**

- ❌ NOT SSH
- ❌ NOT sudo
- ❌ NOT log in with password

**Data impact:**  
Home directory remains untouched

Use this for:
- Security incidents
- Temporary suspension
- Immediate access removal
### `offboard` (Safe exit)

Includes **everything from `revoked`**, plus:
- Home directory is archived:
``` shell
/var/archives/offboard/<username>-<timestamp>.tar.gz
```

- Home directory is **removed from `/home`**
- User account remains (locked)

**Important guarantees:**
- Archive is created **only once**
- Re-running the playbook does **not** create duplicate archives
    

Use this for:
- Employee leaving
- Contractor exit
- Compliance retention
### `decom` (Final decommission)

Includes **everything from `revoked`**, plus:
- If no archive exists yet → archive home
- User account is deleted
- Archive is preserved

**Final state:**
- No login
- No account
- Archive kept for audit / recovery

This is **not reversible** without re-creating the user.
## How to apply changes

You **do not need tags**.

Just update the user `state` and run:

```bash
ansible-playbook playbooks/manage_linux_admins/manage_linux_admins.yml -i inventory/<env>.yml
```

The role automatically:

- Detects what changed
- Applies only the required actions
- Skips safely if nothing is needed
## Rollback rules (Important)

|From → To|Possible?|Notes|
|---|---|---|
|revoked → present|✅ Yes|Keys + group restored|
|offboard → present|⚠️ Partial|User restored, **home must be manually restored from archive**|
|decom → present|❌ No|User must be recreated as new|

This is intentional and protects data integrity.

## 📁 Repository Structure

```
roles/
└── linux_admins/
    ├── tasks/
    │   └── main.yml          # Full lifecycle logic
    ├── handlers/
    │   └── main.yml          # SSH restart handler
    ├── templates/
    │   └── sudoers_admins.j2 # Admin sudo policy
    └── defaults/
        └── main.yml          # Safe defaults
group_vars/
└── all/
    └── admins.yml            # Source of truth for users
playbooks/
└── manage_linux_admins/
    └── manage_linux_admins.yml
```

## ⚙️ Logical Flow (High-level)

```
admins.yml (state)
        |
        v
[ PRESENT ]
        |
        v
[ REVOKED ]  ---> immediate access stop
        |
        v
[ OFFBOARD ] ---> archive + remove home
        |
        v
[ DECOM ]    ---> delete user, keep archive
```

Key design principles:
- **State-driven**
- **Idempotent**
- **No duplicate archives**
- **No destructive defaults**
## Security & Compliance Notes

- SSH access is key-based by default
- Password login hardening can be enabled gradually (canary-safe)
- Admin privileges are explicitly controlled
- Home data is archived before destruction
- Archives are immutable unless manually removed
## Recommended Workflow

1. Add new user as `present`
2. Validate access on 1–2 servers (canary)
3. Roll out to fleet
4. When access must be removed → set `revoked`
5. When user leaves → set `offboard`
6. After retention period → set `decom`
## Why this design works

- No surprise deletions
- No manual SSH cleanup
- Clear audit trail
- Human-readable lifecycle
- Safe by default, strict when needed