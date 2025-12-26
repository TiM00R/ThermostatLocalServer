# ThermostatLocalServer - Documentation Index

Complete documentation for the ThermostatLocalServer project.

---

## Documentation Files

### 1. [README.md](README.md) - Main Documentation ⭐
**Complete system documentation** covering:
- Overview and purpose
- What the system does
- System architecture with diagrams
- Key features (progressive discovery, state change detection, etc.)
- Component descriptions
- Installation & deployment
- Configuration guide
- API reference overview
- Database schema
- Operational details

**Start here** for comprehensive understanding of the system.

---

### 2. [ARCHITECTURE.md](ARCHITECTURE.md) - Technical Architecture 🔧
**Deep technical details** for developers:
- Code organization and project structure
- Data flow diagrams
- Component implementation details
- API implementation internals
- Database operations and queries
- Network protocols (UDP, TCP, HTTP)
- Error handling patterns
- Testing approaches
- Performance tuning

**Use this** when working on the codebase or debugging issues.

---

### 3. [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - Quick Reference Guide 📋
**Command reference** for daily operations:
- Service management (systemd)
- Database operations
- Configuration switching
- Monitoring and logs
- Troubleshooting procedures
- Common tasks
- Emergency procedures
- Useful commands

**Use this** for day-to-day operations and troubleshooting.

---

### 4. [API_REFERENCE.md](API_REFERENCE.md) - Complete API Reference 🌐
**All API endpoints** with examples:
- Local REST API (control thermostats)
- Public Server API (cloud sync)
- RadioThermostat Device API (direct device control)
- Response codes
- Error handling

**Use this** when integrating with the API or building clients.

---

## Quick Navigation

### I want to...

#### **Learn about the system**
→ Start with [README.md](README.md) sections:
1. Overview
2. What This System Does
3. System Architecture
4. Key Features

#### **Install and deploy**
→ [README.md](README.md) → Installation & Deployment
→ Follow deployment scripts in order
→ See `deployment/README.md` for details

#### **Configure for a new location**
→ [README.md](README.md) → Configuration
→ Copy and edit `config/config.yaml.template`
→ See configuration examples

#### **Control thermostats via API**
→ [API_REFERENCE.md](API_REFERENCE.md) → Local REST API
→ Examples: Set temperature, change mode, get status

#### **Troubleshoot issues**
→ [QUICK_REFERENCE.md](QUICK_REFERENCE.md) → Troubleshooting
→ Check service status, logs, database

#### **Understand the code**
→ [ARCHITECTURE.md](ARCHITECTURE.md)
→ Code organization, data flow, components

#### **Monitor the system**
→ [QUICK_REFERENCE.md](QUICK_REFERENCE.md) → Monitoring
→ View logs, check API, database queries

#### **Backup and restore**
→ [QUICK_REFERENCE.md](QUICK_REFERENCE.md) → Backup & Restore
→ Database backup procedures

#### **Optimize performance**
→ [ARCHITECTURE.md](ARCHITECTURE.md) → Performance Tuning
→ Database, polling, network optimization

---

## Additional Documentation

### In Root Directory

**README.md** (Project Root)
- Project overview
- Quick links to detailed docs
- Basic setup instructions

**GITHUB_SETUP.md**
- GitHub repository setup
- Version control guidelines
- Collaboration instructions

---

### In `docs/` Directory

**RadioThermostat_CT50_Honeywell_Wifi_API_V1.3.pdf**
- Official RadioThermostat API specification
- Device commands and responses
- Hardware details

**ssh-tunnel-guide.md**
- SSH reverse tunnel setup
- Remote access configuration
- Security considerations

**nh-house-tunnel-setup-guide.md**
- New Hampshire house specific setup
- Tunnel configuration

**reverse-ssh-tunnel-setup-new-server.md**
- Setting up tunnels for new servers
- Step-by-step instructions

**kill-stale-tunnel-quick-reference.md**
- Troubleshooting SSH tunnels
- Quick commands

---

### In `deployment/` Directory

**README.md**
- Deployment process overview
- Script descriptions
- Multi-location setup

**FILES-TO-MOVE.md**
- Files needed for deployment
- Deployment checklist

---

## Documentation by Use Case

### First-Time Setup

1. Read [README.md](README.md) → Overview & Architecture
2. Follow [README.md](README.md) → Installation & Deployment
3. Configure using [README.md](README.md) → Configuration
4. Test using [QUICK_REFERENCE.md](QUICK_REFERENCE.md) → API Examples

### Daily Operations

1. Service management: [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
2. Monitoring: [QUICK_REFERENCE.md](QUICK_REFERENCE.md) → Monitoring
3. Troubleshooting: [QUICK_REFERENCE.md](QUICK_REFERENCE.md) → Troubleshooting

### Development

1. Code structure: [ARCHITECTURE.md](ARCHITECTURE.md) → Code Organization
2. Component details: [ARCHITECTURE.md](ARCHITECTURE.md) → Component Details
3. Data flow: [ARCHITECTURE.md](ARCHITECTURE.md) → Data Flow
4. Testing: [ARCHITECTURE.md](ARCHITECTURE.md) → Testing

### API Integration

1. Endpoint reference: [API_REFERENCE.md](API_REFERENCE.md)
2. Examples: [API_REFERENCE.md](API_REFERENCE.md) → Each endpoint
3. Error handling: [API_REFERENCE.md](API_REFERENCE.md) → Error Handling

---

## Key Concepts

### Progressive Discovery
Multi-phase device discovery for fast startup:
- **Database Phase**: Test known devices (3s)
- **UDP Phase**: Broadcast discovery (10s)
- **TCP Phase**: Full IP scan (background)

See: [README.md](README.md) → Progressive Discovery System

### State Change Detection
Monitors for manual thermostat adjustments:
- Temperature changes ≥ 0.5°F
- Setpoint, mode, hold changes
- Immediate upload to public server

See: [README.md](README.md) → State Change Detection

### Data Aggregation
5-second polling aggregated to minute-level:
- Average temperature
- HVAC runtime percentage
- Poll success/failure counts

See: [README.md](README.md) → Data Aggregation

### Public Server Sync
Three upload types:
- **Immediate**: State changes (as detected)
- **Status**: Current state (every 30s)
- **Minute**: Aggregations (every 60s)

See: [README.md](README.md) → Public Server Synchronization

### Command Execution
Three command types:
- **set_state**: Temperature, mode, hold
- **set_away_temp**: Away temperature
- **discover_devices**: Network discovery

See: [API_REFERENCE.md](API_REFERENCE.md) → Poll Commands

---

## System Overview Diagram

```
┌────────────────────────────────────────────────┐
│         ThermostatLocalServer                  │
│         (Python FastAPI)                       │
│                                                │
│  Discovery → Polling → Aggregation → Upload   │
│                                                │
└───────┬──────────────────┬─────────────────────┘
        │                  │
        ▼                  ▼
   ┌─────────┐      ┌──────────────┐
   │CT50/CT80│      │  PostgreSQL  │
   │Devices  │      │  Database    │
   └─────────┘      └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │Public Server │
                    │  (HTTPS)     │
                    └──────────────┘
```

---

## Version Information

**Current Version**: 2.0

**Protocol Version**: 2.0 (Discovery Progress)

**API Version**: 2.0

**Last Updated**: December 2024

---

## Getting Help

### Documentation Questions
Check relevant documentation file based on topic:
- System understanding → README.md
- Code/implementation → ARCHITECTURE.md
- Operations/troubleshooting → QUICK_REFERENCE.md
- API usage → API_REFERENCE.md

### Common Issues

**Discovery not finding devices**
→ [QUICK_REFERENCE.md](QUICK_REFERENCE.md) → No Thermostats Discovered

**Database connection failed**
→ [QUICK_REFERENCE.md](QUICK_REFERENCE.md) → Database Connection Failed

**Public server sync issues**
→ [QUICK_REFERENCE.md](QUICK_REFERENCE.md) → Public Server Sync Issues

**Service won't start**
→ [QUICK_REFERENCE.md](QUICK_REFERENCE.md) → Service Won't Start

---

## Contributing

When updating documentation:

1. **README.md**: High-level features, architecture changes
2. **ARCHITECTURE.md**: Code structure, implementation details
3. **QUICK_REFERENCE.md**: New commands, procedures
4. **API_REFERENCE.md**: API endpoint changes

Keep documentation synchronized with code changes.

---

## Documentation Standards

### File Format
- Markdown (.md) format
- GitHub-flavored markdown
- Code blocks with language specification
- Table of contents for long documents

### Code Examples
- Use realistic values
- Include comments where needed
- Show both request and response
- Include error cases

### Commands
- Full command with all flags
- Expected output
- Platform-specific notes (Linux, Windows)

### Updates
- Date documentation changes
- Note version applicability
- Reference related changes

---

*Documentation Index - Last updated December 2024*
