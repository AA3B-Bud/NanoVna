#  NanoVNASaver
#  A python program to view and export Touchstone data from a NanoVNA
#  Copyright (C) 2019.  Rune B. Broberg
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
import logging
import math
import cmath
import io
from NanoVNASaver.RFTools import Datapoint

logger = logging.getLogger(__name__)


class Options:
    # Fun fact: In Touchstone 1.1 spec all params are optional unordered.
    # Just the line has to start with "#"
    UNIT_TO_FACTOR = {
        "ghz": 10**9,
        "mhz": 10**6,
        "khz": 10**3,
        "hz": 10**0,
    }
    VALID_UNITS = UNIT_TO_FACTOR.keys()
    VALID_PARAMETERS = "syzgh"
    VALID_FORMATS = ("ma", "db", "ri")

    def __init__(self,
                 unit: str = "GHZ",
                 parameter: str = "S",
                 t_format: str = "ma",
                 resistance: int = 50):
        # set defaults
        assert unit.lower() in Options.VALID_UNITS
        assert parameter.lower() in Options.VALID_PARAMETERS
        assert t_format.lower() in Options.VALID_FORMATS
        assert resistance > 0
        self.unit = unit.lower()
        self.parameter = parameter.lower()
        self.format = t_format.lower()
        self.resistance = resistance

    @property
    def factor(self):
        return Options.UNIT_TO_FACTOR[self.unit]

    def __str__(self):
        return (
            f"# {self.unit} {self.parameter}"
            f" {self.format} r {self.resistance}"
        ).upper()

    def parse(self, line):
        if not line.startswith("#"):
            raise TypeError("Not an option line: " + line)
        pfact = pparam = pformat = presist = False
        params = iter(line[1:].lower().split())
        for p in params:
            if p in Options.VALID_UNITS and not pfact:
                self.factor = Options.UNIT_TO_FACTOR[p]
                pfact = True
            elif p in Options.VALID_PARAMETERS and not pparam:
                self.parameter = p
                pparam = True
            elif p in Options.VALID_FORMATS and not pformat:
                self.format = p
                pformat = True
            elif p == "r" and not presist:
                self.resistance = int(next(params))
            else:
                raise TypeError("Illegial option line: " + line)


class Touchstone:

    def __init__(self, filename: str):
        self.filename = filename
        self.sdata = [[], [], [], []]  # at max 4 data pairs
        self.comments = []
        self.opts = Options()

    @property
    def s11data(self) -> list:
        return self.sdata[0]

    @property
    def s21data(self) -> list:
        return self.sdata[1]

    @property
    def s12data(self) -> list:
        return self.sdata[2]

    @property
    def s22data(self) -> list:
        return self.sdata[3]

    def _parse_comments(self, fp) -> str:
        for line in fp:
            line = line.strip()
            if line.startswith("!"):
                logger.info(line)
                self.comments.append(line)
                continue
            return line

    def _append_line_data(self, freq: float, data: list):
        data_list = iter(self.sdata)
        vals = iter(data)
        for v in vals:
            if self.opts.format == "ri":
                next(data_list).append(
                    Datapoint(freq, float(v), float(next(vals))))
            if self.opts.format == "ma":
                z = cmath.polar(float(v), float(next(vals)))
                next(data_list).append(Datapoint(freq, z.real, z.imag))
            if self.opts.format == "db":
                z = cmath.polar(math.exp(float(v) / 20), float(next(vals)))
                next(data_list).append(Datapoint(freq, z.real, z.imag))

    def load(self):
        logger.info("Attempting to open file %s", self.filename)
        try:
            with open(self.filename) as infile:
                self.loads(infile.read())
        except TypeError as e:
            logger.exception("Failed to parse %s: %s", self.filename, e)
        except IOError as e:
            logger.exception("Failed to open %s: %s", self.filename, e)

    def loads(self, s: str):
        """Parse touchstone 1.1 string input
           appends to existing sdata if Touchstone object exists
        """
        with io.StringIO(s) as file:
            opts_line = self._parse_comments(file)
            self.opts.parse(opts_line)

            prev_freq = 0.0
            prev_len = 0
            for line in file:
                # ignore empty lines (even if not specified)
                if not line.strip():
                    continue

                # ignore comments at data end
                data = line.split('!')[0]
                data = data.split()
                freq, data = float(data[0]) * self.opts.factor, data[1:]
                data_len = len(data)

                # consistency checks
                if freq <= prev_freq:
                    raise TypeError("Frequeny not ascending: " + line)
                prev_freq = freq

                if prev_len == 0:
                    prev_len = data_len
                    if data_len % 2:
                        raise TypeError("Data values aren't pairs: " + line)
                elif data_len != prev_len:
                    raise TypeError("Inconsistent number of pairs: " + line)

                self._append_line_data(freq, data)

    def setFilename(self, filename):
        self.filename = filename
