from datetime import datetime as dt
import pytz

DEFAULT_LOCAL_TZ = 'Europe/Copenhagen'

def localize_datetime(naive_dt, timezone_str=DEFAULT_LOCAL_TZ):
    """
    Localizes a naive datetime object to the specified timezone.

    Parameters:
    naive_dt (datetime): A naive datetime object (without timezone info).
    timezone_str (str): A string representing the timezone (e.g., 'America/New_York').

    Returns:
    datetime: A timezone-aware datetime object.
    """
    timezone = pytz.timezone(timezone_str)
    localized_dt = timezone.localize(naive_dt)
    return localized_dt

def local_dt_from_utc_str(utc_str, timezone_str=DEFAULT_LOCAL_TZ):
    """
    Converts a UTC datetime string to a timezone-aware datetime object.

    Parameters:
    utc_str (str): A UTC datetime string in the format '%Y-%m-%d %H:%M:%S'.
    timezone_str (str): A string representing the target timezone.

    Returns:
    datetime: A timezone-aware datetime object in the specified timezone.
    """
    #utc_dt = dt.strptime(utc_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=pytz.utc)
    utc_dt = dt.fromisoformat(utc_str)
    target_timezone = pytz.timezone(timezone_str)
    localized_dt = utc_dt.astimezone(target_timezone)
    return localized_dt

def main():

    time_str = '2025-11-03T06:00:00+00:00'
    resu_str = '2025-11-03 06:00:00+00:00'

    #print(pytz.all_timezones)  # Print all available timezones
    #return
    # Example usage

    
    localized_dt = local_dt_from_utc_str(time_str)
    print("Localized datetime:", localized_dt)

if __name__ == "__main__":
    main()