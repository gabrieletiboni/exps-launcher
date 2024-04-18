# Experiments launcher for python scripts (slurm and local)
Handle batch job submissions with ease, both on remote clusters using slurm or locally in background.

### Features tracking

- [X] Automatic wandb group naming from config .yaml files
- [X] Automatic sweep over hyperparameters (`sweep.foo=[1,2,3] sweep.bar=["alice","bob"]`)
- [X] Slurm jobs submission
    - [ ] common config files for different scripts
    - [ ] additive host.time for config files
    - [X] wandb_group_suffix for default wandb name
    - [X] test run on local machine with exps.test=true
    - [ ] host.timefactor : multiply time by this factor for a host in particular
    - [ ] ignore host retrieval when exps.test=true (since it does not matter)
- [X] non-slurm background scripts submission on local machine
- [X] handle cpu cores constraints for local non-slurm scripts

## Installation
```
git clone <this repo>
cd exps_launcher
pip install -r requirements.txt
pip install .
```

## Getting Started
Create the `exps_launcher_configs` directory inside your project directory, following the structure below.
Then, copy the `launch_exps.py` file inside your project directory.

0. `export EXPS_HOSTNAME=<customhostname>`
1. Project structure:
```
.
└── exps_launcher_configs/
    ├── config.yaml              # exps_launcher configs (can be overwritten by cli args exps.<params>)
    ├── host/
    │   ├── default.yaml         # default params for all hosts
    │   ├── host2.yaml           # host-specific sbatch parameters (--partition, --project, ...)
    │   ├── host2.yaml
    │   └── ...
    ├── scripts/
    │   ├── script1/             # `python script1.py ...`
    │   │   ├── default.yaml     # default params for `script1.py`
    │   │   ├── test.yaml        # params for testing with `script.py`
    │   │   ├── conf1.yaml       # configuration
    │   │   └── conf2.yaml
    │   └── script2/
    │       └── ...
    └── sweeps/                  # sweep configurations
        └── fiveseeds.yaml
```
2. Launch `launch_exps.py` script:
    - `python launch_exps.py script=script1 config=[conf1,conf2] sweep.config=[fiveseeds] sweep.foo=[1,10,100]`

Notes:
- subdirs of `scripts/` must be named with the corresponding python script name. E.g. the example above refers to existing python scripts `script1.py` and `script2.py` in your project root dir.
- the `script` parameter is mandatory, and must be a single string. A single script can be launched.
- A sequence of configuration files can be provided with the `config` parameter. Priority is in decreasing order, i.e. conf2 overwrites conf1 in the example above.
- check out the config files above (e.g. `conf1.yaml` and `conf2.yaml`) for quick examples on how to use them.
- sweep parameters like `sweep.foo=[1,10,100]` can also be defined in script-specific config files (e.g. in `conf1.yaml`).
- host parameters like `host.time="03:00:00"` can also be defined in script-specific config files (e.g. in `conf1.yaml`), which overwrite the host definitions. This way you can, e.g., specify different sbatch times for different scripts and their corresponding configurations, or different sbatch names (`host.job-name="myscript")`.
- you can pass `exps.hostname` to overwrite the hostname for the current experiment, e.g. to have different host configurations for the same host

Advanced commands:
- Use exps.<param_name>=<value> for config options. Accepted params are:
  - exps.test=false
  - exps.no_confirmation=false [skip asking for confirmation before actually launching the experiments]
  - exps.fake=false
  - exps.hostname
  - exps.force_hostname_environ=true
  - exps.group_suffix=""  # assumes script has a --group parameter for the wandb group name
  - exps.noslurm=false
  - CPU usage:
    - (noslurm, single script) exps.cpus-list="50,51,52"
    - (noslurm, multiple scripts) exps.cpus-start=50 exps.cpus-per-task=4


## Troubleshooting




