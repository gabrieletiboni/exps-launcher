# Slurm experiments launcher for python scripts
Handle batch job submission on multiple clusters with ease.

This project is a work in progress:
- [ ] SLURM batch job submission
  - [ ] test run
- [ ] parallel python script submissions without slurm, on a local workstation

## Installation
```
git clone <this repo>
cd exps_launcher
pip install -r requirements.txt
pip install .
```

## Getting Started
Include the configuration files in your current project directory, following the project structure below.
Then, use the `launch_exps.py` and its command line parameters to launch experiments.

0. `export EXPS_HOSTNAME=<customhostname>`
1. Project structure:
```
.
└── exps_root/
    ├── config.yaml              # exps_launcher configs (can be overwritten by command exps.<params>)
    ├── host/					 # host-specific sbatch parameters (--partition, --project, ...)
    │   ├── default.yaml         # default params for all hosts
    │   ├── host2.yaml
    │   ├── host2.yaml
    │   └── ...
    ├── scripts/
    │   ├── script1/			 # `python script1.py ...`
    │   │   ├── default.yaml     # default params for `script1.py`
    │   │   ├── test.yaml        # params for testing with `script.py`
    │   │   ├── conf1.yaml
    │   │   └── conf2.yaml
    │   └── script2/
    │       └── ...
    └── sweeps/                  # sweep configurations
        └── fiveseeds.yaml
```
2. Launch `launch_exps.py` script:
	- `launch_exps.py script=script1 config=[conf1,conf2] sweep.config=[fiveseeds] sweep.foo=[1,10,100]`

Notes:
- subdirs of `scripts/` must be named with the corresponding python script name. E.g. the project structure above will call `python script1.py` and `python script2.py` respectively.
- the `script` parameter is mandatory, and must be a single string. A single script can be invoked.
- multiple configurations for the same script can be provided with the `config` parameter. Priority is in decreasing order, i.e. conf2 overwrites conf1 in the example above.
- sweep parameters like `sweep.foo=[1,10,100]` can also be defined in script-specific conf files.
- host parameters like `host.time="03:00:00"` can also be defined in script-specific conf files, which overwrite the host definitions. This way you can specify different sbatch times for different scripts and their corresponding configurations, or different sbatch names.
- you can pass `exps.hostname` to overwrite the hostname for the current experiment, e.g. to have different host configurations for the same host

Advanced commands:
- Use exps.<param_name>=<value> for config options. Accepted params are:
  - exps.test
  - exps.no_confirmation
  - exps.fake
  - exps.hostname
  - exps.force_hostname_environ


## Troubleshooting



