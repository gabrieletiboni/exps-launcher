"""Test exps launcher script

    (Single batch of exps)
        python test.py script=script1 config=conf1 [<overwrite script-specific parameters>]  [host.<overwrite sbatch parameters>] [exps.fake=true]


    (Multiple batches of exps)
        

"""
from exps_launcher.ExpsLauncher import ExpsLauncher

def main():
    expsLauncher = ExpsLauncher(root='exps_launcher_configs',
                                force_hostname_environ=False)

    expsLauncher.launch()

if __name__ == '__main__':
    main()