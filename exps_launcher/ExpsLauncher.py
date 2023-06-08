from typing import Any, Dict, List, Optional, Tuple, Type, Union
import pdb
import os
from copy import deepcopy
import subprocess

try:
    from omegaconf import OmegaConf
except ImportError:
    raise ImportError(f"Package omegaconf not installed.")

from exps_launcher.OmegaConfParser import OmegaConfParser

class ExpsLauncher():
    """Handler class for the Experiment Launcher package"""
    
    def __init__(self,
                 root : str,
                 name : str = '',
                 force_hostname_environ: bool = True,
                 infer_cpus_per_task: bool = True):
        """
            
            root : path to configuration files
            name : name prefix appearing in submitted jobs 
            force_hostname_environ : force environment variable to be set
                                     to recognize current hostname
            infer_cpus_per_task : set cpus-per-task as the --now parameter.
                                  you can overwrite this behavior by passing a custom parameter
                                  from command line
        """
        self.root = os.path.join(root)
        assert os.path.isdir(self.root), f'Given root folder does not exist on current system: {self.root}'
        self.name = name
        self.force_hostname_environ = force_hostname_environ
        self.infer_cpus_per_task = infer_cpus_per_task

        ### Fixed parameters ######################
        self.host_configs_root = 'hosts'
        self.script_configs_root = 'scripts'
        self.hostname_env_variable = 'EXPS_HOSTNAME'
        ###########################################
        
        self.args_parser = OmegaConfParser()

    def multilaunch(self, configs):
        """Launch multiple batches of exps"""
        raise NotImplementedError('Launch multiple instances of exp_launcher.py script through a bash file' \
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
            if choice.lower() in valid_choices:
                if choice.lower() == 'y' or choice.lower() == 'yes':
                    return True
                else:
                    return False
            else:
                print('\nInvalid input.')

    def _get_exps_params(self, cli_args):
        default_exps_params_filename = os.path.join(self.root, 'default.yaml')

        default_exps_params = {}
        if os.path.isfile(default_exps_params_filename):
            default_exps_params = OmegaConf.load(default_exps_params_filename)

        exps_params = {}
        if 'exps' in cli_args:
            exps_params = deepcopy(cli_args.exps)

        exps_params = OmegaConf.merge(default_exps_params, exps_params)

        # Hard code default params if they are not there
        if 'test' not in exps_params:
            exps_params.test = True
        if 'no_confirmation' not in exps_params:
            exps_params.no_confirmation = False

        return exps_params

    def launch(self):
        """
            Use exps.<param> for extra options on this function.
            Accepted params are:

            test : bool, if set, launch the desired script with test parameters to check that
                                 input parameters are correct. Only last conf in the sweep is checked.
            no_confirmation : bool, do not ask for confirmation and do not display summary
        """
        # Read input parameters
        cli_args = self.args_parser.parse_from_cli()

        exps_params = self._get_exps_params(cli_args)
        if 'exps' in cli_args:
            del cli_args.exps

        assert self._check_mandatory_params(cli_args), f'Not all mandatory parameters have been set.'

        # Retrieve current machine's hostname from Environ Variable
        hostname = self._get_hostname()
        
        # Read host configs for SBATCH parameters
        host_configs = self._read_host_configs(hostname)
        host_configs = {'host': host_configs}

        # Get python script parameters
        script_params = self._read_script_configs(cli_args)
        scriptname = str(cli_args.script)+'.py'

        # Merge script configs with host configs, prioritizing script configs
        script_params = OmegaConf.merge(host_configs, script_params)
        self._check_unexpected_script_params(script_params)

        # Get sweep parameters for launching multiple exps. E.g. sweep.seed=[42,43,44]
        sweep_params = self._handle_sweep_params(cli_args, script_params)

        # Get test parameters for test run
        if exps_params.test:
            test_params = self._get_test_params(cli_args)
        else:
            test_params = None

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

        if not exps_params.no_confirmation:
            # Display summary of experiment batch
            self._display_summary(script_params=script_params,
                                  host_params=host_params,
                                  sweep_params=sweep_params,
                                  test_params=test_params)

            if not self.ask_confirmation('Do you wish to launch these experiments? (y/n)'):
                return False


        # execute scripts (--fake option prints the srun commands instead of actually doing them)

    def _check_unexpected_script_params(self, script_configs):
        if 'exps' in script_configs:
            raise ValueError(f'`exps` param should not be controlled in the script parameters')

        # if 'sweep' in script_configs:
        #     raise ValueError(f'`sweep` param should not be controlled in the script parameters')

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
                        assert os.path.isfile(os.path.join(self.root, self.sweep_config_root, self.args_parser.add_extension(sweep_conf_file))),\
                                f'Desired .yaml file does not exist: '\
                                f'{os.path.join(self.root, self.sweep_config_root, self.args_parser.add_extension(sweep_conf_file))}'
                        current =  OmegaConf.load(os.path.join(self.root, self.sweep_config_root, self.args_parser.add_extension(sweep_conf_file)))
                        OmegaConf.merge(sweeps_from_config, current)
                else:
                    sweeps[param] = self.args_parser.as_list(cli_args.sweep[param])
            
            # Merge sweeps, prioritizing sweeps in command line
            sweeps = OmegaConf.merge(sweeps_from_config, sweeps)

        sweep_from_script = {}
        if 'sweep' in script_params:
            sweep_from_script = deepcopy(script_params.sweep)

        sweeps = OmegaConf.merge(sweep_from_script, sweeps)

        return sweeps

    def _run_test(test_params, script_params):
        pass
        # print('...testing...')
        # retcode = subprocess.call(["python", script_params.name])
        # print('Return code of test.py is:', retcode)


    def _display_summary(self, script_params, host_params, sweep_params={}, test_params=None):
        print(f'{"="*40} SUMMARY {"="*40}')

        print('\nSBATCH parameters:', end='')
        print(self.args_parser.pformat_dict(host_params, indent=1))

        print('\nSCRIPT parameters:', end='')
        print(self.args_parser.pformat_dict(script_params, indent=1))

        print('\nSWEEP parameters:', end='')
        print(self.args_parser.pformat_dict(sweep_params, indent=1))

        print('\nTEST parameters:', end='')
        if test_params is not None:
            print(self.args_parser.pformat_dict(test_params, indent=1))
        else:
            print(' NO TEST RUN IS LAUNCHED.')

        n_exps = self._get_n_exps(sweep_params)
        print(f'\nA total number of {n_exps} jobs is requested.')
        print(f'{"="*89}')

    def _get_n_exps(self, sweep_params):
        n_exps = 1
        for k, v in sweep_params.items():
            n_exps *= len(v)
        return n_exps

    def _read_script_configs(self, cli_args):
        assert isinstance(cli_args.script, str)
        scripts_root = os.path.join(self.root, self.script_configs_root, cli_args.script)

        assert os.path.isdir(scripts_root), f'Script dir {scripts_root} not found on current system.' \
                                            'Make sure you create a directory with this name and have subscript' \
                                            '2nd-level config files, including ideally a default.yaml file.'

        default_script_configs, script_configs = {}, {}

        # Make sure either default or corresponding config are defined
        assert os.path.isfile(os.path.join(scripts_root, 'default.yaml')) or 'config' in cli_args, f'No default.yaml' \
                                                                    'was found and no script config file has been' \
                                                                    'provided. Cannot find parameters for this run.' \
                                                                    'Create empty files to provide no input parameters.'

        # Load default file (if it exists)
        if os.path.isfile(os.path.join(scripts_root, 'default.yaml')):
            default_script_configs = OmegaConf.load(os.path.join(scripts_root, 'default.yaml'))
        
        if 'config' in cli_args:
            for conf in cli_args.config:
                assert os.path.isfile(os.path.join(scripts_root, self.args_parser.add_extension(conf))), f'Desired' \
                        f'.yaml file does not exist: {os.path.join(scripts_root, self.args_parser.add_extension(conf))}'
                current =  OmegaConf.load(os.path.join(scripts_root, self.args_parser.add_extension(conf)))
                script_configs = OmegaConf.merge(script_configs, current)

        # Overwrite default values with specific 2nd-level category values
        script_configs = OmegaConf.merge(default_script_configs, script_configs)

        return script_configs

    def _read_host_configs(self, hostname):
        host_root = os.path.join(self.root, self.host_configs_root)

        # Expected host config filename. E.g. exps_root/hosts/lichtenberg.yaml
        config_filename = os.path.join(host_root, hostname+str('.yaml'))
        assert os.path.isfile(config_filename), f'Host config path does not exist on current system: {config_filename}.' \
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
            print(f'`script` parameter must be passed, specifying the correspinding config folder.')
            return False

        return True

    def _check_all_sbatch_params(self, host_params):
        mandatory_params = ['mem-per-cpu', 'time', 'job-name', 'ntasks']
        for mand_param in mandatory_params:
            if mand_param not in host_params:
                print(f'--`{mand_param}` mandatory parameter is missing from the host parameters.')
                return False

        return True


    def _get_hostname(self):
        """Get current machine hostname
            Prioritise the use of the env variable
        """
        if os.environ.get(self.hostname_env_variable) is not None:
            return os.environ.get(self.hostname_env_variable).lower()
        else:
            if self.force_hostname_environ:
                raise ValueError(f'{self.hostname_env_variable} environment variable is not set. Cannot recognize' \
                                 'current hostname. (Set force_hostname_environ=False to automatically detect it)')
            else:
                print(f'--- WARNING! {self.hostname_env_variable} env variable is not defined, so automatic hostname' \
                      'is retrieved instead.')
                return socket.gethostname().lower()