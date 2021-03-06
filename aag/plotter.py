import os
import logging

from yaml import full_load

from datetime import datetime as dt
from datetime import timedelta as tdelta
from dateutil.parser import parse as date_parser

import numpy as np
from pandas.plotting import register_matplotlib_converters

from matplotlib import pyplot as plt
from matplotlib.dates import DateFormatter
from matplotlib.dates import HourLocator
from matplotlib.dates import MinuteLocator
from matplotlib.ticker import FormatStrFormatter
from matplotlib.ticker import MultipleLocator

from astropy.time import Time
from astroplan import Observer
from astropy.coordinates import EarthLocation

logging.basicConfig()
logger = logging.getLogger('aag-weather-plotter')

register_matplotlib_converters()
plt.ioff()
plt.style.use('classic')


def label_pos(lim, pos=0.85):
    return lim[0] + pos * (lim[1] - lim[0])


class WeatherPlotter(object):

    """ Plot weather information for a given time span """

    def __init__(self, data, config_file=None, date_string=None, *args, **kwargs):
        super(WeatherPlotter, self).__init__()
        self.args = args
        self.kwargs = kwargs

        # Read configuration
        try:
            with open(config_file, 'r') as f:
                self.config = full_load(f.read())
        except Exception as e:
            raise e

        try:
            self.cfg = self.config['weather']['plot']
        except KeyError:
            logger.error(f'Invalid configuration file.')

        self.thresholds = self.config['weather'].get('aag_cloud', None)

        if not date_string:
            self.today = True
            self.date = dt.utcnow()
            self.date_string = self.date.strftime('%Y%m%dUT')
            self.start = self.date - tdelta(1, 0)
            self.end = self.date
            self.lhstart = self.date - tdelta(0, 60 * 60)
            self.lhend = self.date + tdelta(0, 5 * 60)

        else:
            self.today = False
            self.date = date_parser(f'{date_string} 23:59:59')
            self.date_string = date_string
            self.start = dt(self.date.year, self.date.month, self.date.day, 0, 0, 0, 0)
            self.end = dt(self.date.year, self.date.month, self.date.day, 23, 59, 59, 0)
        logger.info(f'Creating weather plotter for {self.date_string}')

        # Get objects for plotting location specifics.
        self.observer = self.get_location()
        self.twilights = self.get_twilights()

        # Set up table data.
        self.table = data
        logger.debug(f'Found {len(self.table)} total weather entries.')

        # Filter by date
        logger.debug(f'Filtering table rows for {self.date_string}')
        self.table = self.table.loc[self.start.isoformat():self.end.isoformat()]

        self.time = self.table.index
        self.date_format = '%Y-%m-%d %H:%m:%S'
        first = f'{self.time[0]:{self.date_format}}'
        last = f'{self.time[-1]:{self.date_format}}'
        logger.debug(f'Retrieved {len(self.table)} entries between {first} and {last}')

    def make_plot(self, save_plot=True, output_file=None):
        # -------------------------------------------------------------------------
        # Plot a day's weather
        # -------------------------------------------------------------------------
        start_time = f'{self.start:{self.date_format}}'
        end_time = f'{self.end:{self.date_format}}'

        logger.debug(f'Setting up plot for time range: {start_time} to {end_time}')
        if self.today:
            start_hour = f'{self.lhstart:{self.date_format}}'
            end_hour = f'{self.lhend:{self.date_format}}'
            logger.debug(f'Will generate last hour plot: {start_hour} to {end_hour}')

        self.dpi = self.kwargs.get('dpi', 72)
        self.fig = plt.figure(figsize=(20, 12), dpi=self.dpi)
#         self.axes = plt.gca()
        self.hours = HourLocator(byhour=range(24), interval=1)
        self.hours_fmt = DateFormatter('%H')
        self.mins = MinuteLocator(range(0, 60, 15))
        self.mins_fmt = DateFormatter('%H:%M')
        self.plot_positions = [([0.000, 0.835, 0.700, 0.170], [0.720, 0.835, 0.280, 0.170]),
                               ([0.000, 0.635, 0.700, 0.170], [0.720, 0.635, 0.280, 0.170]),
                               ([0.000, 0.450, 0.700, 0.170], [0.720, 0.450, 0.280, 0.170]),
                               ([0.000, 0.265, 0.700, 0.170], [0.720, 0.265, 0.280, 0.170]),
                               ([0.000, 0.185, 0.700, 0.065], [0.720, 0.185, 0.280, 0.065]),
                               ([0.000, 0.000, 0.700, 0.170], [0.720, 0.000, 0.280, 0.170]),
                               ]
        self.plot_ambient_vs_time()
        self.plot_cloudiness_vs_time()
        self.plot_windspeed_vs_time()
        self.plot_rain_freq_vs_time()
        self.plot_safety_vs_time()
        self.plot_pwm_vs_time()

        if save_plot:
            self.save_plot(plot_filename=output_file)
            # Close all figures to free memory.
            plt.close('all')
        else:
            return self.fig

    def get_location(self):
        location_cfg = self.config.get('location', None)
        location = EarthLocation(
            lat=location_cfg['latitude'],
            lon=location_cfg['longitude'],
            height=location_cfg['elevation'],
        )
        return Observer(location=location,
                        name=location_cfg['name'],
                        timezone=location_cfg['timezone'])

    def get_twilights(self):
        """ Determine sunrise and sunset times """
        logger.debug('Determining sunrise, sunset, and twilight times')

        sunset = self.observer.sun_set_time(Time(self.start), which='next').datetime
        sunrise = self.observer.sun_rise_time(Time(self.start), which='next').datetime

        at_time = Time(self.start)

        # Calculate and order twilights and set plotting alpha for each
        twilights = [(self.start, 'start', 0.0),
                     (sunset, 'sunset', 0.0),
                     (self.observer.twilight_evening_civil(at_time, which='next').datetime, 'ec', 0.1),
                     (self.observer.twilight_evening_nautical(
                         at_time, which='next').datetime, 'en', 0.2),
                     (self.observer.twilight_evening_astronomical(
                         at_time, which='next').datetime, 'ea', 0.3),
                     (self.observer.twilight_morning_astronomical(
                         at_time, which='next').datetime, 'ma', 0.5),
                     (self.observer.twilight_morning_nautical(
                         at_time, which='next').datetime, 'mn', 0.3),
                     (self.observer.twilight_morning_civil(at_time, which='next').datetime, 'mc', 0.2),
                     (sunrise, 'sunrise', 0.1),
                     ]

        twilights.sort(key=lambda x: x[0])
        final = {'sunset': 0.1, 'ec': 0.2, 'en': 0.3, 'ea': 0.5,
                 'ma': 0.3, 'mn': 0.2, 'mc': 0.1, 'sunrise': 0.0}
        twilights.append((self.end, 'end', final[twilights[-1][1]]))

        return twilights

    def plot_ambient_vs_time(self):
        """ Ambient Temperature vs Time """
        logger.debug('Plot Ambient Temperature vs. Time')

        t_axes = self.fig.add_axes(self.plot_positions[0][0])
        if self.today:
            time_title = self.date
        else:
            time_title = self.end

        t_axes.set_title(
            f'{self.observer.name} Weather for {self.date_string} at {time_title:%H:%M:%S}')

        amb_temp = self.table['ambient_temp_C']

        t_axes.plot_date(self.time, amb_temp, 'ko',
                         markersize=2, markeredgewidth=0, drawstyle="default")

        try:
            max_temp = max(amb_temp)
            min_temp = min(amb_temp)
            label_time = self.end - tdelta(0, 6 * 60 * 60)
            label_temp = label_pos(self.cfg['amb_temp_limits'])
            t_axes.annotate('Low: {:4.1f} $^\circ$C, High: {:4.1f} $^\circ$C'.format(
                min_temp, max_temp),
                xy=(label_time, max_temp),
                xytext=(label_time, label_temp),
                size=16,
            )
        except Exception:
            pass

        t_axes.set_ylabel("Ambient Temp. (C)")
        t_axes.grid(which='major', color='k')
        t_axes.set_yticks(range(-100, 100, 10))
        t_axes.set_xlim(self.start, self.end)
        t_axes.set_ylim(self.cfg['amb_temp_limits'])
        t_axes.xaxis.set_major_locator(self.hours)
        t_axes.xaxis.set_major_formatter(self.hours_fmt)

        for i, twi in enumerate(self.twilights):
            if i > 0:
                t_axes.axvspan(self.twilights[i - 1][0], self.twilights[i][0],
                               ymin=0, ymax=1, color='blue', alpha=twi[2])

        if self.today:
            tlh_axes = self.fig.add_axes(self.plot_positions[0][1])
            tlh_axes.set_title('Last Hour')
            tlh_axes.plot_date(self.time, amb_temp, 'ko',
                               markersize=4, markeredgewidth=0,
                               drawstyle="default")
            tlh_axes.plot_date([self.date, self.date], self.cfg['amb_temp_limits'],
                               'g-', alpha=0.4)
            try:
                current_amb_temp = self.current_values['data']['ambient_temp_C']
                current_time = self.current_values['date']
                label_time = current_time - tdelta(0, 58 * 60)
                label_temp = label_pos(self.cfg['amb_temp_limits'])
                tlh_axes.annotate('Currently: {:.1f} $^\circ$C'.format(current_amb_temp),
                                  xy=(current_time, current_amb_temp),
                                  xytext=(label_time, label_temp),
                                  size=16,
                                  )
            except Exception:
                pass

            tlh_axes.grid(which='major', color='k')
            tlh_axes.set_yticks(range(-100, 100, 10))
            tlh_axes.xaxis.set_major_locator(self.mins)
            tlh_axes.xaxis.set_major_formatter(self.mins_fmt)
            tlh_axes.yaxis.set_ticklabels([])
            tlh_axes.set_xlim(self.lhstart, self.lhend)
            tlh_axes.set_ylim(self.cfg['amb_temp_limits'])

    def plot_cloudiness_vs_time(self):
        """ Cloudiness vs Time """
        logger.debug('Plot Temperature Difference vs. Time')
        td_axes = self.fig.add_axes(self.plot_positions[1][0])

        sky_temp_C = self.table['sky_temp_C']
        ambient_temp_C = self.table['ambient_temp_C']
        sky_condition = self.table['sky_condition']

        temp_diff = np.array(sky_temp_C) - np.array(ambient_temp_C)

        td_axes.plot_date(self.time, temp_diff, 'ko-', label='Cloudiness',
                          markersize=2, markeredgewidth=0,
                          drawstyle="default")

        wclear = [(x.strip() == 'Clear') for x in sky_condition]
        td_axes.fill_between(self.time, -60, temp_diff, where=wclear, color='green', alpha=0.5)

        wcloudy = [(x.strip() == 'Cloudy') for x in sky_condition]
        td_axes.fill_between(self.time, -60, temp_diff, where=wcloudy, color='yellow', alpha=0.5)

        wvcloudy = [(x.strip() == 'Very Cloudy') for x in sky_condition]
        td_axes.fill_between(self.time, -60, temp_diff, where=wvcloudy, color='red', alpha=0.5)

        if self.thresholds:
            st = self.thresholds.get('threshold_very_cloudy', None)
            if st:
                td_axes.plot_date([self.start, self.end], [st, st], 'r-',
                                  markersize=2, markeredgewidth=0, alpha=0.3,
                                  drawstyle="default")

        td_axes.set_ylabel("Cloudiness")
        td_axes.grid(which='major', color='k')
        td_axes.set_yticks(range(-100, 100, 10))
        td_axes.set_xlim(self.start, self.end)
        td_axes.set_ylim(self.cfg['cloudiness_limits'])
        td_axes.xaxis.set_major_locator(self.hours)
        td_axes.xaxis.set_major_formatter(self.hours_fmt)
        td_axes.xaxis.set_ticklabels([])

        if self.today:
            tdlh_axes = self.fig.add_axes(self.plot_positions[1][1])
            tdlh_axes.plot_date(self.time, temp_diff, 'ko-',
                                label='Cloudiness', markersize=4,
                                markeredgewidth=0, drawstyle="default")
            tdlh_axes.fill_between(self.time, -60, temp_diff, where=wclear,
                                   color='green', alpha=0.5)
            tdlh_axes.fill_between(self.time, -60, temp_diff, where=wcloudy,
                                   color='yellow', alpha=0.5)
            tdlh_axes.fill_between(self.time, -60, temp_diff, where=wvcloudy,
                                   color='red', alpha=0.5)
            tdlh_axes.plot_date([self.date, self.date], self.cfg['cloudiness_limits'],
                                'g-', alpha=0.4)

            if self.thresholds:
                st = self.thresholds.get('threshold_very_cloudy', None)
                if st:
                    tdlh_axes.plot_date([self.start, self.end], [st, st], 'r-',
                                        markersize=2, markeredgewidth=0, alpha=0.3,
                                        drawstyle="default")

            try:
                current_cloudiness = self.current_values['data']['sky_condition']
                current_time = self.current_values['date']
                label_time = current_time - tdelta(0, 58 * 60)
                label_temp = label_pos(self.cfg['cloudiness_limits'])
                tdlh_axes.annotate('Currently: {:s}'.format(current_cloudiness),
                                   xy=(current_time, label_temp),
                                   xytext=(label_time, label_temp),
                                   size=16,
                                   )
            except Exception:
                pass

            tdlh_axes.grid(which='major', color='k')
            tdlh_axes.set_yticks(range(-100, 100, 10))
            tdlh_axes.set_ylim(self.cfg['cloudiness_limits'])
            tdlh_axes.set_xlim(self.lhstart, self.lhend)
            tdlh_axes.xaxis.set_major_locator(self.mins)
            tdlh_axes.xaxis.set_major_formatter(self.mins_fmt)
            tdlh_axes.xaxis.set_ticklabels([])
            tdlh_axes.yaxis.set_ticklabels([])

    def plot_windspeed_vs_time(self):
        """ Windspeed vs Time """
        logger.debug('Plot Wind Speed vs. Time')
        w_axes = self.fig.add_axes(self.plot_positions[2][0])

        wind_speed = self.table['wind_speed_KPH']
        wind_mavg = moving_average(wind_speed, 9)
        matime, wind_mavg = moving_averagexy(self.time, wind_speed, 9)
        wind_condition = self.table['wind_condition']

        w_axes.plot_date(self.time, wind_speed, 'ko', alpha=0.5,
                         markersize=2, markeredgewidth=0,
                         drawstyle="default")
        w_axes.plot_date(matime, wind_mavg, 'b-',
                         label='Wind Speed',
                         markersize=3, markeredgewidth=0,
                         linewidth=3, alpha=0.5,
                         drawstyle="default")
        w_axes.plot_date([self.start, self.end], [0, 0], 'k-', ms=1)
        wcalm = [(x.strip() == 'Calm') for x in wind_condition]
        w_axes.fill_between(self.time, -5, wind_speed, where=wcalm,
                            color='green', alpha=0.5)
        wwindy = [(x.strip() == 'Windy') for x in wind_condition]
        w_axes.fill_between(self.time, -5, wind_speed, where=wwindy,
                            color='yellow', alpha=0.5)
        wvwindy = [(x.strip() == 'Very Windy') for x in wind_condition]
        w_axes.fill_between(self.time, -5, wind_speed, where=wvwindy,
                            color='red', alpha=0.5)

        if self.thresholds:
            st = self.thresholds.get('threshold_very_windy', None)
            if st:
                w_axes.plot_date([self.start, self.end], [st, st], 'r-',
                                 markersize=2, markeredgewidth=0, alpha=0.3,
                                 drawstyle="default")
            st = self.thresholds.get('threshold_very_gusty', None)
            if st:
                w_axes.plot_date([self.start, self.end], [st, st], 'r-',
                                 markersize=2, markeredgewidth=0, alpha=0.3,
                                 drawstyle="default")

        try:
            max_wind = max(wind_speed)
            label_time = self.end - tdelta(0, 5 * 60 * 60)
            label_wind = label_pos(self.cfg['wind_limits'])
            w_axes.annotate('Max Gust: {:.1f} (km/h)'.format(max_wind),
                            xy=(label_time, label_wind),
                            xytext=(label_time, label_wind),
                            size=16,
                            )
        except Exception:
            pass
        w_axes.set_ylabel("Wind (km/h)")
        w_axes.grid(which='major', color='k')
#         w_axes.yticks(range(0, 200, 10))

        w_axes.set_xlim(self.start, self.end)
        w_axes.set_ylim(self.cfg['wind_limits'])
        w_axes.xaxis.set_major_locator(self.hours)
        w_axes.xaxis.set_major_formatter(self.hours_fmt)
        w_axes.xaxis.set_ticklabels([])
        w_axes.yaxis.set_major_locator(MultipleLocator(20))
        w_axes.yaxis.set_major_formatter(FormatStrFormatter('%d'))
        w_axes.yaxis.set_minor_locator(MultipleLocator(10))

        if self.today:
            wlh_axes = self.fig.add_axes(self.plot_positions[2][1])
            wlh_axes.plot_date(self.time, wind_speed, 'ko', alpha=0.7,
                               markersize=4, markeredgewidth=0,
                               drawstyle="default")
            wlh_axes.plot_date(matime, wind_mavg, 'b-',
                               label='Wind Speed',
                               markersize=2, markeredgewidth=0,
                               linewidth=3, alpha=0.5,
                               drawstyle="default")
            wlh_axes.plot_date([self.start, self.end], [0, 0], 'k-', ms=1)
            wlh_axes.fill_between(self.time, -5, wind_speed, where=wcalm,
                                  color='green', alpha=0.5)
            wlh_axes.fill_between(self.time, -5, wind_speed, where=wwindy,
                                  color='yellow', alpha=0.5)
            wlh_axes.fill_between(self.time, -5, wind_speed, where=wvwindy,
                                  color='red', alpha=0.5)
            wlh_axes.plot_date([self.date, self.date], self.cfg['wind_limits'],
                               'g-', alpha=0.4)

            if self.thresholds:
                st = self.thresholds.get('threshold_very_windy', None)
                if st:
                    wlh_axes.plot_date([self.start, self.end], [st, st], 'r-',
                                       markersize=2, markeredgewidth=0, alpha=0.3,
                                       drawstyle="default")
                st = self.thresholds.get('threshold_very_gusty', None)
                if st:
                    wlh_axes.plot_date([self.start, self.end], [st, st], 'r-',
                                       markersize=2, markeredgewidth=0, alpha=0.3,
                                       drawstyle="default")

            try:
                current_wind = self.current_values['data']['wind_speed_KPH']
                current_time = self.current_values['date']
                label_time = current_time - tdelta(0, 58 * 60)
                label_wind = label_pos(self.cfg['wind_limits'])
                wlh_axes.annotate('Currently: {:.0f} km/h'.format(current_wind),
                                  xy=(current_time, current_wind),
                                  xytext=(label_time, label_wind),
                                  size=16,
                                  )
            except Exception:
                pass
            wlh_axes.grid(which='major', color='k')
#             wlh_axes.yticks(range(0, 200, 10))
            wlh_axes.set_xlim(self.lhstart, self.lhend)
            wlh_axes.set_ylim(self.cfg['wind_limits'])
            wlh_axes.xaxis.set_major_locator(self.mins)
            wlh_axes.xaxis.set_major_formatter(self.mins_fmt)
            wlh_axes.xaxis.set_ticklabels([])
            wlh_axes.yaxis.set_ticklabels([])
            wlh_axes.yaxis.set_major_locator(MultipleLocator(20))
            wlh_axes.yaxis.set_major_formatter(FormatStrFormatter('%d'))
            wlh_axes.yaxis.set_minor_locator(MultipleLocator(10))

    def plot_rain_freq_vs_time(self):
        """ Rain Frequency vs Time """

        logger.debug('Plot Rain Frequency vs. Time')
        rf_axes = self.fig.add_axes(self.plot_positions[3][0])

        rf_value = self.table['rain_frequency']
        rain_condition = self.table['rain_condition']

        rf_axes.plot_date(self.time, rf_value, 'ko-', label='Rain',
                          markersize=2, markeredgewidth=0,
                          drawstyle="default")

        wdry = [(x.strip() == 'Dry') for x in rain_condition]
        rf_axes.fill_between(self.time, 0, rf_value, where=wdry,
                             color='green', alpha=0.5)
        wwet = [(x.strip() == 'Wet') for x in rain_condition]
        rf_axes.fill_between(self.time, 0, rf_value, where=wwet,
                             color='orange', alpha=0.5)
        wrain = [(x.strip() == 'Rain') for x in rain_condition]
        rf_axes.fill_between(self.time, 0, rf_value, where=wrain,
                             color='red', alpha=0.5)

        if self.thresholds:
            st = self.thresholds.get('threshold_wet', None)
            if st:
                rf_axes.plot_date([self.start, self.end], [st, st], 'r-',
                                  markersize=2, markeredgewidth=0, alpha=0.3,
                                  drawstyle="default")

        rf_axes.set_ylabel("Rain Sensor")
        rf_axes.grid(which='major', color='k')
        rf_axes.set_ylim(self.cfg['rain_limits'])
        rf_axes.set_xlim(self.start, self.end)
        rf_axes.xaxis.set_major_locator(self.hours)
        rf_axes.xaxis.set_major_formatter(self.hours_fmt)
        rf_axes.xaxis.set_ticklabels([])

        if self.today:
            rflh_axes = self.fig.add_axes(self.plot_positions[3][1])
            rflh_axes.plot_date(self.time, rf_value, 'ko-', label='Rain',
                                markersize=4, markeredgewidth=0,
                                drawstyle="default")
            rflh_axes.fill_between(self.time, 0, rf_value, where=wdry,
                                   color='green', alpha=0.5)
            rflh_axes.fill_between(self.time, 0, rf_value, where=wwet,
                                   color='orange', alpha=0.5)
            rflh_axes.fill_between(self.time, 0, rf_value, where=wrain,
                                   color='red', alpha=0.5)
            rflh_axes.plot_date([self.date, self.date], self.cfg['rain_limits'],
                                'g-', alpha=0.4)
            if st:
                rflh_axes.plot_date([self.start, self.end], [st, st], 'r-',
                                    markersize=2, markeredgewidth=0, alpha=0.3,
                                    drawstyle="default")

            try:
                current_rain = self.current_values['data']['rain_condition']
                current_time = self.current_values['date']
                label_time = current_time - tdelta(0, 58 * 60)
                label_y = label_pos(self.cfg['rain_limits'])
                rflh_axes.annotate('Currently: {:s}'.format(current_rain),
                                   xy=(current_time, label_y),
                                   xytext=(label_time, label_y),
                                   size=16,
                                   )
            except Exception:
                pass
            rflh_axes.grid(which='major', color='k')
            rflh_axes.set_ylim(self.cfg['rain_limits'])
            rflh_axes.set_xlim(self.lhstart, self.lhend)
            rflh_axes.xaxis.set_major_locator(self.mins)
            rflh_axes.xaxis.set_major_formatter(self.mins_fmt)
            rflh_axes.xaxis.set_ticklabels([])
            rflh_axes.yaxis.set_ticklabels([])

    def plot_safety_vs_time(self):
        """ Plot Safety Values """

        logger.debug('Plot Safe/Unsafe vs. Time')
        safe_axes = self.fig.add_axes(self.plot_positions[4][0])

        safe_value = [int(x) for x in self.table['safe']]

        safe_axes.plot_date(self.time, safe_value, 'ko',
                            markersize=2, markeredgewidth=0,
                            drawstyle="default")
        safe_axes.fill_between(self.time, -1, safe_value,
                               where=(self.table['safe']),
                               color='green', alpha=0.5)
        safe_axes.fill_between(self.time, -1, safe_value,
                               where=(~self.table['safe']),
                               color='red', alpha=0.5)
        safe_axes.set_ylabel("Safe")
        safe_axes.set_xlim(self.start, self.end)
        safe_axes.set_ylim(-0.1, 1.1)
        safe_axes.set_yticks([0, 1])
        safe_axes.grid(which='major', color='k')
        safe_axes.xaxis.set_major_locator(self.hours)
        safe_axes.xaxis.set_major_formatter(self.hours_fmt)
        safe_axes.xaxis.set_ticklabels([])
        safe_axes.yaxis.set_ticklabels([])

        if self.today:
            safelh_axes = self.fig.add_axes(self.plot_positions[4][1])
            safelh_axes.plot_date(self.time, safe_value, 'ko-',
                                  markersize=4, markeredgewidth=0,
                                  drawstyle="default")
            safelh_axes.fill_between(self.time, -1, safe_value,
                                     where=(self.table['safe']),
                                     color='green', alpha=0.5)
            safelh_axes.fill_between(self.time, -1, safe_value,
                                     where=(~self.table['safe']),
                                     color='red', alpha=0.5)
            safelh_axes.plot_date([self.date, self.date], [-0.1, 1.1],
                                  'g-', alpha=0.4)
            try:
                safe = self.current_values['data']['safe']
                current_safe = {True: 'Safe', False: 'Unsafe'}[safe]
                current_time = self.current_values['date']
                label_time = current_time - tdelta(0, 58 * 60)
                label_y = 0.35
                safelh_axes.annotate('Currently: {:s}'.format(current_safe),
                                     xy=(current_time, label_y),
                                     xytext=(label_time, label_y),
                                     size=16,
                                     )
            except Exception:
                pass
            safelh_axes.set_ylim(-0.1, 1.1)
            safelh_axes.set_yticks([0, 1])
            safelh_axes.grid(which='major', color='k')
            safelh_axes.set_xlim(self.lhstart, self.lhend)
            safelh_axes.xaxis.set_major_locator(self.mins)
            safelh_axes.xaxis.set_major_formatter(self.mins_fmt)
            safelh_axes.xaxis.set_ticklabels([])
            safelh_axes.yaxis.set_ticklabels([])

    def plot_pwm_vs_time(self):
        """ Plot Heater values """

        logger.debug('Plot PWM Value vs. Time')
        pwm_axes = self.fig.add_axes(self.plot_positions[5][0])
        pwm_axes.set_ylabel("Heater (%)")
        pwm_axes.set_ylim(self.cfg['pwm_limits'])
        pwm_axes.set_yticks([0, 25, 50, 75, 100])
        pwm_axes.set_xlim(self.start, self.end)
        pwm_axes.grid(which='major', color='k')
        rst_axes = pwm_axes.twinx()
        rst_axes.set_ylim(-1, 21)
        rst_axes.set_xlim(self.start, self.end)

        pwm_value = self.table['pwm_value']
        rst_delta = self.table['rain_sensor_temp_C'].astype('float') - self.table['ambient_temp_C']

        rst_axes.plot_date(self.time, rst_delta, 'ro-', alpha=0.5,
                           label='RST Delta (C)',
                           markersize=2, markeredgewidth=0,
                           drawstyle="default")

        # Add line with same style as above in order to get in to the legend
        pwm_axes.plot_date([self.start, self.end], [-10, -10], 'ro-',
                           markersize=2, markeredgewidth=0,
                           label='RST Delta (C)')
        pwm_axes.plot_date(self.time, pwm_value, 'bo-', label='Heater',
                           markersize=2, markeredgewidth=0,
                           drawstyle="default")
        pwm_axes.xaxis.set_major_locator(self.hours)
        pwm_axes.xaxis.set_major_formatter(self.hours_fmt)
        pwm_axes.legend(loc='best')

        if self.today:
            pwmlh_axes = self.fig.add_axes(self.plot_positions[5][1])
            pwmlh_axes.set_ylim(self.cfg['pwm_limits'])
            pwmlh_axes.set_yticks([0, 25, 50, 75, 100])
            pwmlh_axes.set_xlim(self.lhstart, self.lhend)
            pwmlh_axes.grid(which='major', color='k')
            rstlh_axes = pwmlh_axes.twinx()
            rstlh_axes.set_ylim(-1, 21)
            rstlh_axes.set_xlim(self.lhstart, self.lhend)
            rstlh_axes.plot_date(self.time, rst_delta, 'ro-', alpha=0.5,
                                 label='RST Delta (C)',
                                 markersize=4, markeredgewidth=0,
                                 drawstyle="default")
            rstlh_axes.plot_date([self.date, self.date], [-1, 21],
                                 'g-', alpha=0.4)
            rstlh_axes.xaxis.set_ticklabels([])
            rstlh_axes.yaxis.set_ticklabels([])
            pwmlh_axes.plot_date(self.time, pwm_value, 'bo', label='Heater',
                                 markersize=4, markeredgewidth=0,
                                 drawstyle="default")
            pwmlh_axes.xaxis.set_major_locator(self.mins)
            pwmlh_axes.xaxis.set_major_formatter(self.mins_fmt)
            pwmlh_axes.yaxis.set_ticklabels([])

    def save_plot(self, plot_filename=None):
        """ Save the plot to file """

        if plot_filename is None:
            if self.today:
                plot_filename = 'today.png'
            else:
                plot_filename = '{}.png'.format(self.date_string)

            plot_filename = os.path.join(os.path.expandvars(
                '$PANDIR'), 'images', 'weather_plots', plot_filename)

        plot_filename = os.path.abspath(plot_filename)
        plot_dir = os.path.dirname(plot_filename)
        os.makedirs(plot_dir, exist_ok=True)

        logger.info(f'Saving weather plot: {plot_filename}')
        self.fig.savefig(
            plot_filename,
            dpi=self.dpi,
            bbox_inches='tight',
            bbox_extra_artists=[],  # https://github.com/panoptes/POCS/issues/528
            pad_inches=0.10
        )


def moving_average(interval, window_size):
    """ A simple moving average function """
    if window_size > len(interval):
        window_size = len(interval)
    window = np.ones(int(window_size)) / float(window_size)
    return np.convolve(interval, window, 'same')


def moving_averagexy(x, y, window_size):
    if window_size > len(y):
        window_size = len(y)
    if window_size % 2 == 0:
        window_size += 1
    nxtrim = int((window_size - 1) / 2)
    window = np.ones(int(window_size)) / float(window_size)
    yma = np.convolve(y, window, 'valid')
    xma = x[2 * nxtrim:]
    assert len(xma) == len(yma)
    return xma, yma
