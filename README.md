# PyCam project repo

## Documentation

Detailed user and quick start guides can be found at [volcanotech.org](https://www.volcanotech.org/software.html)  

## Pre-requsities

- Windows 10/11
- `conda` installed ([Download page and installation instructions](https://conda-forge.org/download/))
- `git` installed (optional but recommended; [installation instructions](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git))

### Note

The commands outlined below can be run directly in the 'Miniforge prompt' installed with `conda`/`conda-forge`.  
Alternatively, you can run these commands in 'Powershell' once you have made `conda` available to 'Powershell'. You can do this by opening the 'Miniforge prompt' and running `conda init powershell`

## Installation instructions

1. If you have `git` installed then clone the PyCamPermanent repo and move into the PyCamPermanent directory:

```sh
git clone https://github.com/twVolc/PyCamPermanent.git
cd PyCamPermanent
```

- If you don't have `git` installed you can still download and extract [the repository](https://github.com/ubdbra001/PyCamPermanent/tree/standalone) (for instructions, see 'If All Else Fails, Get The Code' on [this page](https://www.howtogeek.com/827348/how-to-download-files-from-github/))
  - Once downloaded you need to extract the files from the zipped file and navigate to the newly extracted directory in your terminal

2. Create a new `python 3.8` conda environment and activate it:

```sh
conda create -n pycam python=3.8
conda activate pycam
```

3. Install dependencies from the requirements.txt file:

```sh
pip install -r requirements.txt
```

4. Run `pycam`:

```sh
python run_pycam.py
```
