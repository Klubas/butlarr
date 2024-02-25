# Butlarr
> Your personal butler for all your *arr* needs

## Why use Butlarr
*Butlarr* is a telegram bot that allows the interaction of multiple people with *arr* instances.
It allows the addition and managment of movies, series, and more to come.

*Butlarr* has been created with hackability and base-compatibility in mind.
If you have a service that behaves logically the same as Sonarr or Radarr it will be compatible with *Butlarr*.
Even if it is not compatible, it is relatively simple to extend the exesting code base for various other services.

## Usage
After following the *Setup* and *Configuration*, ensure that the bot is running.
If not you can start it using: `python -m butlarr` from the repository directory.
Open the telegram chat to the bot and authorize yourself using your previously set `AUTH_PASSWORD`:
```
/auth <A_SECURE_PASSWORD>
```
Show a basic help page using `/help`
To add a movie for example, you could send `/movie Alvin`

![image](https://github.com/TrimVis/butlarr/assets/29759576/089bb19a-01d6-4d89-bc92-f42128200bf0)
![image](https://github.com/TrimVis/butlarr/assets/29759576/9bb30521-ba02-4045-9e1a-06e425d64ce7)

## Installation
### Setup
1. First clone the repository and cd into it
```bash
git clone git@github.com:TrimVis/butlarr.git && cd butlarr
```
2. (Optional) Create a new venv & source it
```bash
python -m venv venv && source venv/bin/activate
```
3. Install dependencies
```bash
python -m venv venv && source venv/bin/activate
```
4. Configure butlarr (see *Configuration*)
5. Start the service
```bash
python -m buttlarr
```

### Configuration
After cloning the repository and `cd`ing into the repository, create a new file at `buttlarr/config/secrets.py`.
Paste and adapt the following template `secrets.py`:
```python
TELEGRAM_TOKEN = "<YOUR_TELEGRAM_TOKEN>"
AUTH_PASSWORD = "<A_SECURE_PASSWORD>"

API_HOSTS = [
    "http://localhost:7878/", # Radarr Instance
    "http://localhost:8989/", # Sonarr Instance
    "http://localhost:8990/", # 2nd Sonarr Instance (E.g. Anime)
]
API_KEYS = [
    "<RADARR_1_API_KEY>", # Radarr Instance
    "<SONARR_1_API_KEY>", # Sonarr Instance
    "<SONARR_2_API_KEY>"  # 2nd Sonarr Instance
]
```

### Systemd service
Create a new file under `/etc/systemd/user` (recommended: `/etc/systemd/user/butlarr.service`)
The new file should have following content (you have to adapt the `REPO_PATH`):
```
[Unit]
Description      = Butlarr Telegram Bot for Arr Service Managment
After            = network.target
After            = systemd-user-sessions.service
After            = network-online.target

[Service]
Type              = simple
WorkingDirectory  = /home/peasant/butlarr
ExecStart         = /bin/bash -c 'source venv/bin/activate; python -m buttlarr'
ExecReload        = /bin/kill -s HUP $MAINPID
KillMode          = mixed
TimeoutStopSec    = 300
Restart           = always
RestartSec        = 60
SyslogIdentifier  = buttlar

[Install]
WantedBy         = multi-user.target
```

Start it using: `systemctl --user start butlarr`
Enable it to start on reboots using: `systemctl --user enable butlarr`


## Open TODOs:
 - [ ] Fix the 'buttler' typo (rename all 'buttlarr' references to 'butlarr')
 - [ ] Create docker instructions
 - [ ] Create a pip package
