# energy-report

Generate energy report from NEM meter data files

## Energy Data

First, request your energy data in NEM12 format from your DNSP (eg. [Ergon][1] or [Energex][2]).

[1]: https://www.ergon.com.au/network/connections/metering/accessing-your-metering-data
[2]: https://www.energex.com.au/home/our-services/meters/accessing-your-metering-data

## Usage

Install python and then this library with:

```sh
python -m pip install nemreport
```

Copy your NEM12 file(s) into a `data/` folder and then run:

```sh
python -m nemreport build
```

## Output

This will then open a report with analysis of your data in a browser.

![](screenshot.png)