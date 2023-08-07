from setuptools import setup, find_packages

setup(name='exps_launcher',
      version='0.0.1',
      scripts=['launch_exps'] ,
      # install_requires=['numpy'],  # And any other dependencies foo needs
      packages=find_packages(exclude=["exps_launcher_configs"]),
      # package_data={'exps_launcher': ['data/*.txt']},
      # include_package_data=True,
)