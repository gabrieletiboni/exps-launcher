from typing import Any, Dict, List, Optional, Tuple, Type, Union
import pdb
import os
import socket
from copy import deepcopy
import subprocess
import sys

from sklearn.model_selection import ParameterGrid
try:
    from omegaconf import OmegaConf
except ImportError:
    raise ImportError(f"Package omegaconf not installed.")

from exps_launcher.OmegaConfParser import OmegaConfParser

class ExpsLauncher():
    """Handler class for the Experiment Launcher package"""
    
    def __init__(self,
                 root : str,
                 infer_cpus_per_task: bool = True):
        """
            
            root : path to configuration files
            infer_cpus_per_task : set cpus-per-task as the --now parameter.
                                  you can overwrite this behavior by passing a custom parameter
                                  from command line
        """
        self.root = os.path.join(root)
        assert os.path.isdir(self.root), f'Given root folder does not exist on current system: {self.root}'
        self.run_logs = os.path.join(self.root, 'run_logs')
        if not os.path.isdir(self.run_logs):
            self.create_dirs(self.run_logs)
        self.infer_cpus_per_task = infer_cpus_per_task

        ### Fixed parameters ######################
        self.host_configs_root = 'hosts'
        self.script_configs_root = 'scripts'
        self.sweep_configs_root = 'sweeps'
        self.hostname_env_variable = 'EXPS_HOSTNAME'
        ###########################################
        
        self.args_parser = OmegaConfParser()

    def multilaunch(self, configs):
        """Launch multiple batches of exps"""
        raise NotImplementedError('Launching multiple instances of exp_launcher.py script through a bash file' \
                                  'is the current preferred way to go about launching multiple batches of experiments.')
        # if isinstance(configs, str):
        #     configs = [configs]

        # if not self.ask_confirmation('Are you sure you want to execute multiple batch experiments without' \
        #                              'asking confirmation for each of them? (y/n)'):
        #     return False

        # for config in configs:
        #     self.launch(args_from_config=config, no_confirmation=True)

    def ask_confirmation(self, msg):
        print(f'\n\n-> {msg}')

        valid_choices = ['y','n', 'yes', 'no']
        while True:
            choice = input()
            print()
            if choice.lower() in valid_choices:
                if choice.lower() == 'y' or choice.lower() == 'yes':
                    return True
                else:
                    return False
            else:
                print('\nInvalid input.')

    def _get_exps_params(self, cli_args):
        default_exps_params_filename = os.path.join(self.root, 'config.yaml')

        default_exps_params = {}
        if os.path.isfile(default_exps_params_filename):
            default_exps_params = OmegaConf.load(default_exps_params_filename)

        exps_params = {}
        if 'exps' in cli_args:
            exps_params = deepcopy(cli_args.exps)

        exps_params = OmegaConf.merge(default_exps_params, exps_params)

        # Hard code default boolean params if they are not in the config.yaml file
        defaults = {'test': False, 'no_confirmation': False, 'fake': False, 'preview': False, 'force_hostname_environ': True}
        for k, v in defaults.items():
            if k not in exps_params:
                exps_params[k] = v
            else:
                assert exps_params[k] is not None, f'parameter exps.{k} should be a boolean, not None.'

        return exps_params

    def launch(self):
        """
            Use cliargs of type exps.<param> for extra options on this function.
            Accepted params are:

            exps.test : bool, if set, launch the desired script with test parameters to check that
                                 input parameters are correct. Only first sweep configuration is checked.
            exps.no_confirmation : bool, do not ask for confirmation and do not display summary
            exps.fake : bool, prints out the slurm job submission commands instead of running them
            exps.preview : bool, prints out all slurm instructions that would be run
            exps.force_hostname_environ : force environment variable to be set
                                          to recognize current hostname
        """
        # Read input parameters
        cli_args = self.args_parser.parse_from_cli()

        exps_params = self._get_exps_params(cli_args)
        if 'exps' in cli_args:
            del cli_args.exps

        assert self._check_mandatory_params(cli_args), f'Not all mandatory parameters have been set.'

        # Retrieve current machine's hostname from Environ Variable
        hostname = self._get_hostname(exps_params=exps_params)
        
        # Read host configs for SBATCH parameters
        host_configs = self._read_host_configs(hostname)
        host_configs = {'host': host_configs}

        # Get python script parameters
        script_params, script_config_names = self._read_script_configs(cli_args)
        scriptname = cli_args.script

        # Merge script configs with host configs, prioritizing script configs
        script_params = OmegaConf.merge(host_configs, script_params)
        self._check_unexpected_script_params(script_params)

        # Get sweep parameters for launching multiple exps. E.g. sweep.seed=[42,43,44]
        sweep_params, cli_args, script_params = self._handle_sweep_params(cli_args, script_params)

        # Get parameters for test run
        if exps_params.test:
            test_params = self._get_test_params(cli_args)
            script_params = OmegaConf.merge(script_params, test_params)
        

        # Merge script parameters in cli_args with script_params, prioritizing cli_args
        del cli_args.script
        if 'config' in cli_args:
            del cli_args.config
        if 'exps' in cli_args:
            del cli_args.exps
        if 'sweep' in cli_args:
            del cli_args.sweep
        if 'sweep' in script_params:
            del script_params.sweep

        configs = OmegaConf.merge(script_params, cli_args)
        
        # Isolate script parameters only
        script_params = deepcopy(configs)
        del script_params.host

        # Isolate host parameters only
        host_params = self.args_parser.to_dict(configs.host)

        wandb_group_name = self.handle_wandb_group_name(script_params, script_config_names, exps_params)
        if wandb_group_name is not None:
            script_params.group = wandb_group_name

        if not exps_params.no_confirmation:
            # Display summary of experiment batch
            self._display_summary(scriptname=scriptname,
                                  script_params=script_params,
                                  host_params=host_params,
                                  sweep_params=sweep_params,
                                  test=exps_params.test,
                                  preview_jobs=exps_params.preview)

            if not exps_params.test and not self.ask_confirmation('Do you wish to launch these experiments? (y/n)'):
                return False

        self._launch_jobs(
                          host_params=host_params,
                          script_params=script_params,
                          sweep_params=sweep_params,
                          default_name=scriptname,
                          fake=exps_params.fake,

                          # Run one local test run without slurm if exps.test=true
                          with_slurm=True if not exps_params.test else False,
                          max_runs=None if not exps_params.test else 1
                        )

    def _launch_jobs(self, host_params, script_params, sweep_params, default_name, fake=False, max_runs=None, with_slurm=True):
        """Formats slurm strings and launches all jobs
            
            fake: prints slurm instructions instead of running them
        """
        with_slurm = True if with_slurm and len(host_params) != 0 else False

        for i, sweep_config in enumerate(ParameterGrid(dict(sweep_params))):
            if max_runs is not None and i >= max_runs:
                return
            command = ''

            if with_slurm:
                command += f'sbatch '
                command += self._format_host_params(host_params, default_name=default_name)
                command += '--wrap \''  # wrap python command
            command += f'python {default_name}.py '
            command += self._format_script_params(script_params)
            command += self._format_sweep_config(sweep_config)
            if with_slurm:
                command += '\''  # end of --wrap command

            self._execute(command, fake=fake)


    def _execute(self, command, fake=False):
        """Execute command on the shell"""        
        if fake:
            print(command)
        else:
            subprocess.run(command, shell=True)


    def _format_host_params(self, host_params, default_name):
        """Returns formatted string for job parameters
        when launching slurm command inline"""
        string = ''
        for k, v in host_params.items():
            assert not self.args_parser.is_list(v), 'Host parameters are not expected to be lists. These should be strings.'
            if v != '' and v is not None:
                string += f'--{k}="{v}" '

        if 'job-name' not in host_params:
            string += f'--job-name="{default_name}" '

        # Hard-code ntasks to 1, if not present
        if 'ntasks' not in host_params:
            string += f'--ntasks=1 '

        if len(host_params) != 0:
            assert 'time' in host_params, 'You are required to specify a time parameter for your slurm jobs.'

        return string


    def _format_script_params(self, script_params):
        """Returns formatted string with script-specific parameters"""
        string = ''
        for k, v in script_params.items():
            if self.args_parser.is_list(v):
                # list parameter
                string += f'--{k} '
                for single_v in v:
                    string += f'{single_v} '
            elif self.args_parser.is_boolean(v):
                if v: 
                    string += f'--{k} '
            else:
                string += f'--{k}="{v}" '
        return string


    def _format_sweep_config(self, sweet_config):
        string = ''
        for k, v in sweet_config.items():
            string += f'--{k}={v} '
        return string


    def _check_unexpected_script_params(self, script_configs):
        if 'exps' in script_configs:
            raise ValueError(f'`exps` param should not be controlled in the script parameters. `exps` key is reserved for exps_launcher parameters.')


    def handle_wandb_group_name(self, script_params, script_config_names, exps_params):
        """Make sure a wandb group has been defined if wandb online mode is active"""
        if 'wandb' in script_params and script_params['wandb'] == 'online':
            if 'group' not in script_params:
                group_name = self.get_default_wandb_group(script_config_names)
                if 'group_suffix' in exps_params:
                    group_name += exps_params.group_suffix

                print(f'--- WARNING! A wandb group has not been defined and wandb is running in online mode. ' \
                      f'Default group name will be: {group_name}')
                
                return group_name
        else:
            return None

    def get_default_wandb_group(self, script_config_names):
        """Concatenate all config files names for default
           wandb group name
        """
        string = ''
        for word in script_config_names:
            string += word[0].upper()+word[1:]+'_'

        return string[:-1]


    def _get_test_params(self, cli_args):
        test_params_filename = os.path.join(self.root, self.script_configs_root, cli_args.script, 'test.yaml')
        assert os.path.isfile(test_params_filename), f'No test.yaml found at {test_params_filename}.' \
                                                      'but exps.test parameter=True.'
        
        test_params = OmegaConf.load(test_params_filename)
        return test_params


    def _handle_sweep_params(self, cli_args, script_params):
        """Get all sweep parameters"""
        sweeps = {}
        sweeps_from_config = {}
        if 'sweep' in cli_args:
            for param in cli_args.sweep:
                # Load sweep config files
                if param == 'config':
                    sweep_conf_files = self.args_parser.as_list(cli_args.sweep[param])
                    for sweep_conf_file in sweep_conf_files:
                        assert os.path.isfile(os.path.join(self.root, self.sweep_configs_root, self.args_parser.add_extension(sweep_conf_file))),\
                                f'Desired .yaml file does not exist: '\
                                f'{os.path.join(self.root, self.sweep_configs_root, self.args_parser.add_extension(sweep_conf_file))}'
                        current =  OmegaConf.load(os.path.join(self.root, self.sweep_configs_root, self.args_parser.add_extension(sweep_conf_file)))
                        sweeps_from_config = OmegaConf.merge(sweeps_from_config, current)
                else:
                    sweeps[param] = self.args_parser.as_list(cli_args.sweep[param])
            
            # Merge sweeps, prioritizing sweeps in command line
            sweeps = OmegaConf.merge(sweeps_from_config, sweeps)

        sweep_from_script = {}
        if 'sweep' in script_params:
            for param in script_params.sweep:
                sweep_from_script[param] = self.args_parser.as_list(script_params.sweep[param])
        sweeps = OmegaConf.merge(sweep_from_script, sweeps)

        # Delete sweep parameters that have been explicitly defined in the cli_args
        overwritten_sweep_values = {}
        values_overwitten_with = {}
        for k, v in sweeps.items():
            if k in cli_args:
                overwritten_sweep_values[k] = v
                values_overwitten_with[k] = cli_args[k]
                delattr(sweeps, k)
        if len(overwritten_sweep_values) != 0:
            print(f'--- WARNING! Sweep parameters {overwritten_sweep_values} have been overwritten by single parameter values specified in the command line {values_overwitten_with}') 

        # Overwrite parameters defined both in the sweep and as single script parameters (prioritizing sweep)
        overwritten_script_params = {}
        values_overwitten_with = {}
        for k, v in sweeps.items():            
            if k in script_params:
                overwritten_script_params[k] = script_params[k]
                values_overwitten_with[k] = v
                delattr(script_params, k)
        if len(overwritten_script_params) != 0:
            print(f'--- WARNING! Parameters {overwritten_script_params} defined explicitly have been overwritten by the sweep.<name> counterpart values {values_overwitten_with}')

        return sweeps, cli_args, script_params


    def _display_summary(self, scriptname, script_params, host_params, sweep_params={}, test=False, preview_jobs=False):
        print(f'{"="*40} SUMMARY {"="*40}')
        print(f'\nScript: {scriptname}.py')
        print('\nSBATCH parameters:', end='')
        print(self.args_parser.pformat_dict(host_params, indent=1))

        print('\nSCRIPT parameters:', end='')
        print(self.args_parser.pformat_dict(script_params, indent=1))

        print('\nSWEEP parameters:', end='')
        print(self.args_parser.pformat_dict(sweep_params, indent=1))

        n_exps = self._get_n_exps(sweep_params)
        print(f'\nA total number of {n_exps} jobs is requested.')

        if preview_jobs:
            print(f'\nPreview of slurm instructions that will be launched:')
            self._launch_jobs(
                              host_params=host_params,
                              script_params=script_params,
                              sweep_params=sweep_params,
                              default_name=scriptname,
                              fake=True,  # fake: simply print them

                              # Run a local test run without slurm if exps.test=true
                              with_slurm=True if not test else False,
                              max_runs=None if not test else 1
                            )
        print(f'{"="*89}')

    def _get_n_exps(self, sweep_params):
        n_exps = 1
        for k, v in sweep_params.items():
            n_exps *= len(v)
        return n_exps

    def _read_script_configs(self, cli_args):
        assert isinstance(cli_args.script, str)
        scripts_root = os.path.join(self.root, self.script_configs_root, cli_args.script)

        assert os.path.isdir(scripts_root), f'Script dir {scripts_root} not found on current system. ' \
                                            'Make sure you create a directory with this name and have subscript ' \
                                            '2nd-level config files, including ideally a default.yaml file.'

        default_script_configs, script_configs = {}, {}

        # Make sure either default or corresponding config are defined
        assert os.path.isfile(os.path.join(scripts_root, 'default.yaml')) or 'config' in cli_args, f'No default.yaml ' \
                                                                    'was found and no script config file has been ' \
                                                                    'provided. Cannot find parameters for this run. ' \
                                                                    'Create empty files to provide no input parameters.'

        # Load default file (if it exists)
        if os.path.isfile(os.path.join(scripts_root, 'default.yaml')):
            default_script_configs = OmegaConf.load(os.path.join(scripts_root, 'default.yaml'))
        
        config_names = []
        if 'config' in cli_args:
            for conf in cli_args.config:
                assert os.path.isfile(os.path.join(scripts_root, self.args_parser.add_extension(conf))), f'Desired ' \
                        f'.yaml file does not exist: {os.path.join(scripts_root, self.args_parser.add_extension(conf))}'
                current =  OmegaConf.load(os.path.join(scripts_root, self.args_parser.add_extension(conf)))
                script_configs = OmegaConf.merge(script_configs, current)
                config_names.append(conf)

        # Overwrite default values with specific 2nd-level category values
        script_configs = OmegaConf.merge(default_script_configs, script_configs)

        return script_configs, config_names

    def _read_host_configs(self, hostname):
        host_root = os.path.join(self.root, self.host_configs_root)

        # Expected host config filename. E.g. exps_root/hosts/lichtenberg.yaml
        config_filename = os.path.join(host_root, hostname+str('.yaml'))
        assert os.path.isfile(config_filename), f'Host config path does not exist on current system: {config_filename}. ' \
                                                'Make sure that you create a yaml config file for this hostname.'

        host_configs = OmegaConf.load(config_filename)

        # Load default file (if it exists)
        if os.path.isfile(os.path.join(host_root, 'default.yaml')):
            default_host_configs = OmegaConf.load(os.path.join(host_root, 'default.yaml'))
            # Merge, priority on host_configs
            host_configs = OmegaConf.merge(default_host_configs, host_configs)

        return host_configs

    def _check_mandatory_params(self, args):
        if 'script' not in args:
            print(f'`script` parameter must be passed, specifying the corresponding config folder.')
            return False

        return True

    def _check_all_sbatch_params(self, host_params):
        mandatory_params = ['mem-per-cpu', 'time', 'job-name', 'ntasks']
        for mand_param in mandatory_params:
            if mand_param not in host_params:
                print(f'--`{mand_param}` mandatory parameter is missing from the host parameters.')
                return False

        return True


    def _get_hostname(self, exps_params):
        """Get current machine hostname
            Prioritise the use of the env variable
        """
        if 'hostname' in exps_params and exps_params.hostname is not None and exps_params.hostname != '':
            return exps_params.hostname

        if os.environ.get(self.hostname_env_variable) is not None:
            return os.environ.get(self.hostname_env_variable).lower()
        else:
            if exps_params.force_hostname_environ:
                raise ValueError(f'{self.hostname_env_variable} environment variable is not set. Cannot recognize ' \
                                 f'current hostname. (Set config exps.force_hostname_environ=False to automatically detect it as: "{socket.gethostname().lower()}")')
            else:
                print(f'--- WARNING! {self.hostname_env_variable} env variable is not defined, so automatic hostname "{socket.gethostname().lower()}" ' \
                      'is retrieved instead.')
                return socket.gethostname().lower()


    def create_dirs(self, path):
        try:
            os.makedirs(os.path.join(path))
        except OSError as error:
            pass