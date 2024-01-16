# Exposure Timing - NEXTA Analysis

We try here to automate decode LED patterns into timing information. There is a lot of work to do here.

Currently it requires you to set up your own python environment to run, but eventually we should have some binaries you can just run and download.

Current GUI is provided by opencv, but we'll quickly need to move to another tool kit. Tk or Qt perhaps.

# Quick Start

```bash
cd nexta_analysis
poetry install
poetry shell
python led_selector.py -i ./example_files/registration_image.fits -o registration.json
```

You should see the following:
![Succesful Registration](getting_started1.jpg)

You can then try to get timing information.

```bash
python read_time.py -r registration.json -o aLight_010-timing.json -i ./example_files/aLight_010.fits
```


# Notes

 * [EasyROI](https://github.com/saharshleo/easyROI) - is a mirrored copy mainly because of pip dependency conflict