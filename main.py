import requests
import os
from datetime import datetime, timedelta, time
from typing import Dict, List

# this key is publically accessible
BASE_HEADER = {"Authorization": 'Bearer ResyAPI api_key="VbWk7s3L4KiK5fzlO7JD3Q5EYolJI7n5"'}

PAYMENT_ID = os.getenv('RESY_PAYMENT_ID')  
RESY_PASS = os.getenv('RESY_PASS')

NUM_SEATS = os.getenv('NUM_SEATS', 2)
VENUE_IDS = os.getenv('VENUE_ID_STRS', "443;1505") # 443: i sodi, 1505: don angie


def get_auth_headers() -> Dict:
    data = {
        "email": "elibailey97@gmail.com",
        "password": RESY_PASS
    }
    resp = requests.post("https://api.resy.com/3/auth/password", headers=BASE_HEADER, data=data)
    resp.raise_for_status()
    res_dict = resp.json()

    headers = {
        "X-Resy-Auth-Token": f"{res_dict.get('token')}",
        "X-Resy-Universal-Auth": f"{res_dict.get('token')}",
        "Authorization": 'Bearer ResyAPI api_key="VbWk7s3L4KiK5fzlO7JD3Q5EYolJI7n5"',
    }
    return headers


def get_user_reservations(headers: Dict) -> List:
    resp = requests.get(
        url="https://api.resy.com/3/user/reservations?limit=10&offset=1&type=upcoming&book_on_behalf_of=false",
        headers=headers)
    resp.raise_for_status()
    return resp.json().get('reservations', [])


def venue_id_in_resys(reservations: List, venue_id: str) -> bool:
    for r in reservations:
        existing_venue = r.get('venue', {}).get('id')
        if str(existing_venue) == venue_id:
            return True
    return False


def get_date(offset_days: int = 0) -> str:
    """Get today's date or the date adjusted by offset_days"""
    now = datetime.now() + timedelta(days=offset_days)
    return now.strftime("%Y-%m-%d")


def days_with_available_reservations(venue_id: str, start_date: str, end_date: str)  -> List:
    "look for a reservation between start and end dates"
    url = f"https://api.resy.com/4/venue/calendar?venue_id={venue_id}&num_seats={NUM_SEATS}&start_date={start_date}&end_date={end_date}"
    res = requests.get(url, headers=BASE_HEADER)
    res.raise_for_status()
    d = res.json()

    out = []
    cal = d.get('scheduled', [])
    for d in cal:
        avail_res = d.get("inventory", {}).get("reservation", "")
        if avail_res.lower() == "available":
            out.append(d)
    return out


def first_well_timed_reservation(
        venue_id: str, 
        available_days: List, 
        day_times: List = None
    ):
    """"""

    # default times, tuple with (start, end) where start and end are (hour, minutes)
    if day_times is None:
        day_times = [((18, 0),(19, 45)), ((19, 0),(19, 45)), ((19, 0),(19, 45)), ((19, 0),(19, 45)), ((18, 0),(19, 45)), ((18, 0),(19, 45)), ((18, 0),(19, 45))]

    for d in available_days:
        # make a request for the time slots this day
        try:
            res = find_reservation_slots(venue_id, d.get('date'))
            slots = res.get('results', {}).get('venues', [])[0].get('slots', [])
            for s in slots:
                start_dt = s.get('date', {}).get('start', "")
                dt = datetime.strptime(start_dt, '%Y-%m-%d %H:%M:%S')
                
                # build time bounds based on weekday (0 = monday, 6 = sunday)
                wkday = dt.weekday()
                day_tuple = day_times[wkday]
                lower_bound = time(hour=day_tuple[0][0], minute=day_tuple[0][1])
                upper_bound = time(hour=day_tuple[1][0], minute=day_tuple[1][1])
                
                if lower_bound <= dt.time() and dt.time() <= upper_bound:
                    return (s, dt.date())

        except Exception as e:
            pass
    
    print(f"no well timed reservations found for venue id {venue_id}")
    return


def find_reservation_slots(venue_id: str, date_str: str):
    """Get slots for a specific venue and day"""
    url = f"https://api.resy.com/4/find?day={date_str}&party_size={NUM_SEATS}&venue_id={venue_id}&sort_by=available&lat=40.779226&location=ny&long=-73.945223"
    res = requests.get(url, headers=BASE_HEADER)
    res.raise_for_status()
    return res.json()


def book(slot, date, id_headers):
    """
    Get a book token and make a booking for a reservation slot
    """
    bt = ""
    # get book token
    config_id = slot.get('config', {}).get('token')
    body = {
        "commit": 0,
        "config_id": config_id,
        "day": str(date),
        "party_size": NUM_SEATS
    }
    headers = id_headers.copy()
    headers["Content-Type"] = "application/json"
    url = "https://api.resy.com/3/details"
    for i in range(1, 6):
        res = requests.request("POST", url, json=body, headers=headers)
        if res.status_code == 201:
            bt = res.json().get('book_token', {}).get('value', "")
            break
        
        body["commit"] = i

    assert bt != ""

    # book
    body = {
        "struct_payment_method": "{\"id\":" + str(PAYMENT_ID) + "}",
        "book_token": bt,
        "source_id": "resy.com-venue-details"
    }
    headers = id_headers.copy()
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    url = f"https://api.resy.com/3/book"
    res = requests.request("POST", url, data=body, headers=id_headers)
    res.raise_for_status()


def make_reservation(venue_id: str, id_headers):
    """
    Check if user has reservation for the desired venue
    If not attempt to get one
    """
    resys = get_user_reservations(id_headers)
    if venue_id_in_resys(resys, venue_id):
        print(f"reservation already exists for venue id {venue_id}")
        return

    # look for a reservation
    start_date = get_date(offset_days=1)
    end_date = get_date(offset_days=365)
    avail_days = days_with_available_reservations(venue_id, start_date, end_date)
    tup = first_well_timed_reservation(venue_id, avail_days)
    if tup:
        # make reservation
        book(tup[0], tup[1], id_headers)
        print(f"reservation made for {venue_id}")


def main():
    id_headers = get_auth_headers()
    for venue_id in VENUE_IDS.split(";"):
        make_reservation(str(venue_id), id_headers)


if __name__ == "__main__":
    main()

