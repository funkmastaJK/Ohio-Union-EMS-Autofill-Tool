"""
Ohio Union EMS Autofill Tool
Copyright (c) 2017 Samuel Yun

This is a tool to auto-fill the EMS paperwork for the Ohio Union AV managers.
This tool is provided as-is and is under active development.

INSTRUCTIONS:
 - edit settings.json with your information
 - "python3 autofill_tool.py" to run tool.

"""
from selenium import webdriver
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import TimeoutException
import selenium.common.exceptions as SeleniumExceptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import sys
import os
import json
import datetime
import logging as logger

# global variables
settings = dict()


class EMS:
    """ Contains functions related to EMS """

    def __init__(self, selenium_webdriver, logging, schedule, year, month, day):
        self.driver = selenium_webdriver
        self.logger = logging
        self.schedule = schedule
        self.year = str(year)
        self.month = str(month)
        self.day = str(day)

        self.setup_ems()

    # region Selenium wrappers
    def wait_for_element_visible(self, css_selector, timeout=30, raise_exception=True):
        """ Waits for the element to be visible. Defaults to waiting 30s

        Args:
            css_selector (str): The CSS selector for the element
            timeout (int): The time in seconds to wait
            raise_exception (bool): Whether to raise exception

        Returns:
            webelement: The webelement corresponding to the CSS selector. None if can't find element

        Raises:
            TimeoutException: raise_exception == True and can't find element
        """

        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
            )
            return element
        except TimeoutException:
            if raise_exception:
                raise TimeoutException("Couldn't find element with CSS selector: '{}'".format(css_selector))
            else:
                return None

    def wait_for_presence_of_all_elements(self, css_selector, timeout=30, raise_exception=True):
        """ Waits for the elements to be visible. Defaults to waiting 30s

        Args:
            css_selector (str): The CSS selector for the element
            timeout (int): The time in seconds to wait
            raise_exception (bool): Whether to raise exception

        Returns:
            list of webelement: The webelements corresponding to the CSS selector. None if can't find element

        Raises:
            TimeoutException: raise_exception == True and can't find element
        """

        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, css_selector))
            )
            return element
        except TimeoutException:
            if raise_exception:
                raise TimeoutException("Couldn't find element with CSS selector: '{}'".format(css_selector))
            else:
                return None

    def wait_for_invisibility_of_element(self, css_selector, timeout=30):
        """ Waits for the elements to be invisible. Defaults to waiting 30s

        Args:
            css_selector (str): The CSS selector for the element
            timeout (int): The time in seconds to wait

        Returns:
            invisible (bool): True if element is invisible, False otherwise
        """

        element = WebDriverWait(self.driver, timeout).until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, css_selector))
        )
        return element
    # endregion

    def navigate_to_event_listing_page(self, select_position=True):
        # Navigate to EMS
        self.driver.get('http://ohiounion.osu.edu/ems')

        # If not logged in, log in.
        if self.driver.title == "Login Required | The Ohio State University":
            input_user = self.wait_for_element_visible("#username")
            input_user.send_keys(settings["ems_username"])

            input_pass = self.wait_for_element_visible("#password")
            input_pass.send_keys(settings["ems_password"])
            input_pass.send_keys(u'\ue007')

        if self.driver.title == "Login Required | The Ohio State University":
            raise RuntimeError("Invalid EMS credentials")

        # If select position, log in as manager
        if select_position:
            self.driver.get("https://ohiounion.osu.edu/secure/ems/")

        if self.driver.current_url == "https://ohiounion.osu.edu/secure/ems/":
            try:
                select = Select(self.wait_for_element_visible("#ctl00_ContentPlaceHolder1_ddl_position"))
                select.select_by_visible_text(settings["manager_position"])
                self.wait_for_element_visible("#ctl00_ContentPlaceHolder1_btn_submit").click()
            except NoSuchElementException:
                raise NoSuchElementException("Unable to find '{}' in EMS position list. Are you a manager?"
                                             .format(settings["manager_position"]))

    def format_date(self):
        """ Formats date in MM/DD/YYYY format

        Returns:
            str: formatted date in MM/DD/YYYY
        """

        formatted_date = self.month + "/" + self.day + "/" + self.year

        self.logger.debug("Formatted date is '{}'".format(formatted_date))

        return formatted_date

    def setup_ems(self):
        """ Performs setup for the script.
         - Navigates to page
         - Logs into EMS, goes to the date given in class instantiation
        """

        formatted_date = self.format_date()

        # navigate to event listing page
        self.logger.info("Navigating to event listing page")
        self.navigate_to_event_listing_page()

        # Go to date
        self.logger.info("Going to date '{}'".format(formatted_date))
        self.wait_for_element_visible("#ctl00_ContentPlaceHolder1_txt_date").click()
        self.wait_for_element_visible("#ctl00_ContentPlaceHolder1_txt_date").clear()
        self.wait_for_element_visible("#ctl00_ContentPlaceHolder1_txt_date").send_keys(formatted_date)
        self.wait_for_element_visible(".container-fluid > h2").click()
        self.wait_for_invisibility_of_element("#ui-datepicker-div")
        self.wait_for_element_visible("#ctl00_ContentPlaceHolder1_btn_submit").click()

    def get_list_of_events(self):
        """ From the Ohio Union Daily Setup Schedule page, gets each pair of
        rows and returns them

        Returns:
            list_events: A list containing 2-tuples with the two rows for an event
        """
        self.logger.info("Getting list of events")

        # Get rows
        list_of_rows = self.wait_for_presence_of_all_elements(".table-responsive > table > tbody > tr")
        list_of_rows.pop(0)

        # split rows into events
        list_events = []
        for row_1, row_2 in zip(list_of_rows[0::2], list_of_rows[1::2]):
            self.logger.info("appending event: '{}".format(row_1.text))
            list_events.append((row_1, row_2))

        return list_events

    def get_list_of_javascript(self, event_list):
        """ Takes a list of events (from get_list_of_events()) and pulls the
        javascript calls to navigate to the event detail page for each event.
        Uses "skip_already_confirmed", "skip_already_scheduled", "skip_rooms",
        and "skip_following_rooms" in settings.json

        Args:
            event_list (list): List containing 2-tuples that are the first and
            second rows of each event

        Returns:
            js_list (list): List containing strings that are the js calls
        """
        self.logger.info("Getting list of javascript")

        js_list = []
        for tup in event_list:
            first_row = tup[0]
            second_row = tup[1]

            room = first_row.find_element_by_css_selector("td:nth-of-type(4)").text
            name = first_row.find_element_by_css_selector("td:nth-of-type(5)").text
            resnum = first_row.find_element_by_css_selector("td:nth-of-type(6)").text
            self.logger.info("Checking event '{0}' in room '{1}' with reservation # '{2}'".format(name, room, resnum))

            # check if already scheduled
            if settings["skip_already_scheduled"]:
                setup_time = first_row.find_element_by_css_selector("td:nth-of-type(7)").text
                checkin_time = first_row.find_element_by_css_selector("td:nth-of-type(8)").text
                teardown_time = first_row.find_element_by_css_selector("td:nth-of-type(9)").text

                if setup_time != " " or checkin_time != " " or teardown_time != " ":
                    self.logger.info("Event is already scheduled")
                    continue

            # check if already confirmed
            if settings["skip_already_confirmed"]:
                setup_confirm = second_row.find_element_by_css_selector("td:nth-of-type(4)").text
                checkin_confirm = second_row.find_element_by_css_selector("td:nth-of-type(5)").text
                teardown_confirm = second_row.find_element_by_css_selector("td:nth-of-type(6)").text

                if setup_confirm != "Confirmed" or checkin_confirm != "Confirmed" or teardown_confirm != "Confirmed":
                    self.logger.info("Event is already confirmed")
                    continue

            # check if skip rooms
            if settings["skip_rooms"]:
                room_name = first_row.find_element_by_css_selector("td:nth-of-type(4)").text
                if room_name in settings["skip_following_rooms"]:
                    self.logger.info("Room should be skipped")
                    continue

            # get javascript command to go to page
            self.logger.info("Event will be scheduled")
            js_command = first_row.find_element_by_css_selector("td:nth-of-type(5) > a").get_attribute("href")
            splitted_command_list = js_command.split(":")
            js_list.append(splitted_command_list[1])

        return js_list

    def schedule_event(self, js_command):
        """ Takes the javascript command to navigate to the event page from the
        Ohio Union Daily Setup Schedule page. Schedules the event based on
        input from schedule. Also uses "skip_events_with_no_av" to skip events
        without any AV equipment listed.

        Args:
            js_command (string): the Javascript command to navigate to the event
            page.
        """

        # check page is on events page
        if self.driver.current_url != "https://ohiounion.osu.edu/ems/":
            self.navigate_to_event_listing_page(select_position=False)

        # navigate to the Event Details page
        self.driver.execute_script(js_command)
        self.wait_for_element_visible(".container-fluid")

        # check page is actually on Event Details page
        title = self.driver.title
        if title != "EMS - Event Details Page":
            raise RuntimeError("Page wasn't on the Event Details Page. Title was '{}'".format(title))

        # get event name
        event_name = self.wait_for_element_visible("h3").text

        # check event has AV
        try:
            if self.wait_for_element_visible(".div_right_column > h5:nth-of-type(1)").text == "A/V Equipment":
                av_equipment = self.wait_for_presence_of_all_elements(".div_right_column > ul:nth-of-type(1) > li")
                if av_equipment[0].text == "None Found":
                    self.logger.info("Event '{}' has no AV".format(event_name))
                    return
            else:
                self.logger.warning("For event '{}', first <h5> is not 'A/V Equipment'")
                return
        except TimeoutException:
            self.logger.warning("For event '{}', timed out")
            return

        # check if event is already scheduled -> refresh js links
        if settings["skip_already_scheduled"]:
            table = self.wait_for_element_visible("#ctl00_ContentPlaceHolder1_dg_staff_assignments")
            table_rows = table.find_elements_by_css_selector("tr")
            for row in table_rows:
                if "Setup" in row.find_element_by_css_selector("td:nth-of-type(1)").text \
                        or "Check-In" in row.find_element_by_css_selector("td:nth-of-type(1)").text \
                        or "Teardown" in row.find_element_by_css_selector("td:nth-of-type(1)").text:
                    self.logger.info("Event '{}' is already scheduled. Need to refresh links.".format(event_name))
                    return True

        # check if event is a room that should be skipped -> refresh js links
        if settings["skip_rooms"]:
            full_room_name = self.wait_for_element_visible("#spRoom").text
            self.logger.info("For event '{0}', in room '{1}', checking if room should be skipped"
                             .format(event_name, full_room_name))
            for name in settings["skip_following_rooms"]:
                if name in full_room_name:
                    self.logger.info("Event '{0}' is in room '{1}' that should be skipped. Need to refresh links"
                                     .format(event_name, name))
                    return True

        # get the time for the event and parse it
        time_for_event = self.wait_for_element_visible("#spRunTime").text
        time_for_event_split = time_for_event.split(' - ')
        event_start_time = time_for_event_split[0]
        event_end_time = time_for_event_split[1]
        self.logger.info("Event '{0}' Start: '{1}' End: '{2}'".format(event_name, event_start_time, event_end_time))

        event_start_dt, event_end_dt = self.convert_times_to_datetime(event_start_time, event_end_time)

        # get assignment info
        try:
            setup_person, setup_time = self.find_setup_info(event_start_dt)
            checkin_person, checkin_time = self.find_checkin_info(event_start_dt)
            teardown_person, teardown_time = self.find_teardown_info(event_end_dt)
            self.logger.info("For event '{0}', setup: '{1}' @ '{2}' checkin: '{3}' @ '{4} teardown: '{5}' @ '{6}'"
                             .format(event_name,
                                     setup_person,
                                     setup_time,
                                     checkin_person,
                                     checkin_time,
                                     teardown_person,
                                     teardown_time))
        except TypeError:
            self.logger.warning("For event '{}', TypeError caught.'".format(event_name))
            return

        # Enter assignments
        self.assign_setup(setup_person, setup_time)
        self.assign_checkin(checkin_person, checkin_time)
        self.assign_teardown(teardown_person, teardown_time)
        self.logger.info("Event '{}' scheduled successfully".format(event_name))

    def enter_assignment(self, person, time_to_enter, assignment):
        """ From the event details page, enters the staff assignments, submit,
        check for errors, and check it was entered.

        Args:
            person (str): name of staff to assign (in format 'Last, First')
            time_to_enter (str): time to assign (in format '12:00 AM')
            assignment (str): assignment. Valid types are: 'Setup', 'Check-In',
                'Teardown'
        """
        if person == "(Unassigned)":
            return

        self.select_staff(person)
        self.select_assignment(assignment)
        self.enter_time(time_to_enter)
        self.wait_for_element_visible("#ctl00_ContentPlaceHolder1_btn_add_staff_assignments").click()

        # check assigned correctly
        table = self.wait_for_element_visible("#ctl00_ContentPlaceHolder1_dg_staff_assignments")
        table_rows = table.find_elements_by_css_selector("tr")
        found = False
        for row in table_rows:
            assign_type = row.find_element_by_css_selector("td:nth-of-type(1)").text
            if assignment in assign_type:
                staff_name = row.find_element_by_css_selector("td:nth-of-type(2)").text
                if person in staff_name:
                    assign_time = row.find_element_by_css_selector("td:nth-of-type(3)").text
                    if time_to_enter in assign_time:
                        found = True
                        break

        if not found:
            self.logger.warning("After assigning '{0}' to '{1}' at '{2}', assignment wasn't found in the table.".format
                                (person, assignment, time))

    def assign_setup(self, person, setup_time):
        """ Assigns the setup to the given person at the given time.

        Args:
            person (str): Person to assign setup. Format 'Last, First'
            setup_time (str): Time to assign setup. Format '12:00 AM'
        """
        self.enter_assignment(person, setup_time, "Setup")

    def assign_checkin(self, person, checkin_time):
        """ Assigns the check-in to the given person at the given time.

        Args:
            person (str): Person to assign to check-in. Format 'Last, First'
            checkin_time (str): Time to assign to check-in. Format '12:00 AM'
        """
        self.enter_assignment(person, checkin_time, "Check-In")

    def assign_teardown(self, person, teardown_time):
        """ Assigns the teardown to the given person at the given time.

        Args:
            person (str): Person to assign to teardown. Format 'Last, First'
            teardown_time (str): Time to assign to teardown. Format '12:00 AM'
        """
        self.enter_assignment(person, teardown_time, "Teardown")

    def find_worker_at_time(self, time_dt):
        """ Given a time, finds a worker who works during that time. Follows order
        in settings["order_to_assign_general_shift"]

        Args:
            time_dt (datetime.py): time of event

        Returns:
            dict: keys: "last_name" and "first_name"
        """

        self.logger.debug("Finding worker for time: {}".format(time_dt.strftime("%H:%M")))
        ending_shift = {}
        for shift_position in settings["order_to_assign_general_shift"]:
            self.logger.debug("For position: {}".format(shift_position))
            for worker in schedule[shift_position]:
                self.logger.debug("    Checking worker: {}".format(worker["last_name"] + " , " + worker["first_name"]))
                start_time, end_time = self.convert_times_to_datetime(worker["start_time"], worker["end_time"])
                if self.compare_times(start_time, time_dt) <= 0 and self.compare_times(end_time, time_dt) == 1:
                    self.logger.debug("    Found worker!")
                    return worker
                elif self.compare_times(start_time, time_dt) <= 0 and self.compare_times(end_time, time_dt) <= 0:
                    if ending_shift == {}:
                        self.logger.debug("   Worker is possibly the last worker of the night")
                        ending_shift = {"end_time": end_time,
                                        "last_name": worker["last_name"],
                                        "first_name": worker["first_name"],
                                        "position": shift_position}
                    elif self.compare_times(end_time, ending_shift["end_time"]) < 0:
                        self.logger.debug("   Worker is possibly the last worker of the night")
                        ending_shift = {"end_time": end_time,
                                        "last_name": worker["last_name"],
                                        "first_name": worker["first_name"],
                                        "position": shift_position}
                    elif "Manager" in shift_position:
                        self.logger.debug("    Checking if worker is the last worker of the night")
                        if self.compare_times(ending_shift["end_time"], time_dt) <= 0:
                            self.logger.debug("    Worker is possibly the last worker of the night")
                            ending_shift = {"end_time": end_time,
                                            "last_name": worker["last_name"],
                                            "first_name": worker["first_name"]}
                        else:
                            self.logger.debug("    Worker is not the last worker of the night")

        if ending_shift == ():
            self.logger.info("Time '{}' has no workers".format(time_dt.strftime("%H:%M")))
            return {"last_name": "{Unassigned}", "first_name": "{Unassigned}"}
        else:
            self.logger.info("Time '{0}' has worker '{1}, '{2}'".format(time_dt.strftime("%H:%M"),
                                                                         ending_shift["last_name"],
                                                                         ending_shift["first_name"]))
            return {"last_name": ending_shift["last_name"], "first_name": ending_shift["first_name"]}
        # Managers only?

    def find_setup_info(self, event_start_time):
        """ Given an event start time, find the correct person to setup the event
        and when to setup the event.

        Start by looking at the shift leads. If there is a shift lead whose shift
        starts at or before the setup time and ends after the setup time, setup
        is assigned to that lead. If there are no shift leads who fit, start
        looking at the managers. If there is a manager whose shift starts at or
        before the setup time and ends after the setup time, setup is assigned to
        that manager. If nobody fits, nobody is assigned to that shift.

        Args:
            event_start_time (datetime.datetime): Time the event starts

        Returns:
            setup_info (2-tuple): First element is the name of person (in the
            format 'Last, First') and second element is the time to assign (in the
            format '12:00 AM'). If nobody can be assigned to the setup, return "(Unassigned)", "12:00 AM"
        """

        setup_dt = self.get_setup_time(event_start_time)
        setup_time = self.convert_datetime_to_time(setup_dt)
        if setup_time == settings["setup_time_night_before"]:
            staff = settings["current_manager_last_name"] + ", " + settings["current_manager_first_name"]
            return staff, setup_time

        person = self.find_worker_at_time(setup_dt)

        if person["last_name"] == "{Unassigned}":
            return "(Unassigned)", "12:00 AM"
        else:
            name = person["last_name"] + ", " + person["first_name"]
            return name, setup_time

    def find_checkin_info(self, event_start_time):
        """ Given an event start time, find the correct person to check-in the
        event and when to check-in the event.

        Start by looking at the shift leads. If there is a shift lead whose shift
        starts at or before the check-in time and ends after the check-in time,
        check-in is assigned to that lead. If there are no shift leads who fit,
        start looking at the managers. If there is a manager whose shift starts at
        or before the check-in time and ends after the check-in time, check-in is
        assigned to that manager. If nobody fits, nobody is assigned to that shift.

        Args:
            event_start_time (datetime.datetime): Time the event starts (in the format '12:00 AM')

        Returns:
            checkin_info (2-tuple): First element is the name of person (in the
            format 'Last, First') and second element is the time to assign (in the
            format '12:00 AM'). If nobody can be assigned to the check-in, return
            "(Unassigned)", "12:00 AM"
        """

        checkin_dt = self.get_checkin_time(event_start_time)
        checkin_time = self.convert_datetime_to_time(checkin_dt)

        person = self.find_worker_at_time(checkin_dt)

        if person["last_name"] == "{Unassigned}":
            return "(Unassigned)", "12:00 AM"
        else:
            name = person["last_name"] + ", " + person["first_name"]
            return name, checkin_time

    def find_teardown_info(self, event_end_time):
        """ Given an event end time, find the correct person to teardown the
        event and when to teardown the event.

        Start by looking at the shift leads. If there is a shift lead whose shift
        starts at or before the teardown time and ends after the teardown time,
        teardown is assigned to that lead. If there are no shift leads who fit,
        start looking at the managers. If there is a manager whose shift starts at
        or before the teardown time and ends after the teardown time, teardown is
        assigned to that manager. If nobody fits, nobody is assigned to that shift.

        Args:
            event_end_time (datetime.datetime): Time the event ends (in the format '12:00 AM')

        Returns:
            teardown_info (2-tuple): First element is the name of person (in the
            format 'Last, First') and second element is the time to assign (in the
            format '12:00 AM'). If nobody can be assigned to the teardown, return
            "(Unassigned)", "12:00 AM"
        """

        teardown_dt = self.get_teardown_time(event_end_time)
        teardown_time = self.convert_datetime_to_time(teardown_dt)

        person = self.find_worker_at_time(teardown_dt)

        if person["last_name"] == "{Unassigned}":
            return "(Unassigned)", "12:00 AM"
        else:
            name = person["last_name"] + ", " + person["first_name"]
            return name, teardown_time

    def parse_time(self, time_to_parse):
        """ Parse a time in the format '12:00 AM' into three parts: hour, minute,
        AM/PM.

        Args:
            time_to_parse (str): time in format '12:00 AM'

        Returns:
            parsed_time (3-tuple): first element is the hour as an int, second
                element is the minute as an int, and third element is the AM/PM as a str
        """

        time_split = time_to_parse.split(' ')
        time_number_part_split = time_split[0].split(':')
        time_first_number = int(time_number_part_split[0])
        time_second_number = int(time_number_part_split[1])
        time_ampm_part = time_split[1]
        self.logger.debug("Parsed '{0}' into '{1}', '{2}', '{3}'".format(time_to_parse,
                                                                         time_first_number,
                                                                         time_second_number,
                                                                         time_ampm_part))

        return time_first_number, time_second_number, time_ampm_part

    def convert_times_to_datetime(self, start_time, end_time):
        """ Given a start and end time, converts the two times to DateTime objects.

        Args:
            start_time (str): Start time. In the form '12:00 AM'
            end_time (str): End time. In the form '12:00 AM'

        Returns:
            start_time_dt (datetime.datetime): Start time as a datetime.
            end_time_dt (datetime.datetime): End time as a datetime.
        """

        start_time_first_part, start_time_second_part, start_time_ampm_part = self.parse_time(start_time)
        end_time_first_part, end_time_second_part, end_time_ampm_part = self.parse_time(end_time)

        if start_time_ampm_part == "AM":
            if start_time_first_part == 12:  # eg 12:30 AM
                start_time_dt = datetime.datetime(2016, 1, 1, 0, start_time_second_part)
            else:  # eg 8:30 AM
                start_time_dt = datetime.datetime(2016, 1, 1, start_time_first_part, start_time_second_part)
        else:
            if start_time_first_part == 12:  # eg 12:30 PM
                start_time_dt = datetime.datetime(2016, 1, 1, 12, start_time_second_part)
            else:  # eg 4:30 PM
                start_time_dt = datetime.datetime(2016, 1, 1, start_time_first_part + 12, start_time_second_part)

        if end_time_ampm_part == "AM" and start_time_ampm_part == "AM":
            if end_time_first_part == 12:  # eg 8:30 AM start, 12:30 AM end
                end_time_dt = datetime.datetime(2016, 1, 2, 0, end_time_second_part)
            else:  # eg 8:30 AM start, 9:30 AM end
                end_time_dt = datetime.datetime(2016, 1, 1, end_time_first_part, end_time_second_part)
        elif end_time_ampm_part == "AM" and start_time_ampm_part == "PM":
            if end_time_first_part == 12:  # eg 8:00 PM start, 12:00 AM end
                end_time_dt = datetime.datetime(2016, 1, 2, 0, end_time_second_part)
            else:  # eg 8:00 PM start, 1:00 AM end
                end_time_dt = datetime.datetime(2016, 1, 2, end_time_first_part, end_time_second_part)
        else:
            if end_time_first_part == 12:  # eg 12:00 PM end
                end_time_dt = datetime.datetime(2016, 1, 1, 12, end_time_second_part)
            else:  # eg 7:00 PM end
                end_time_dt = datetime.datetime(2016, 1, 1, end_time_first_part + 12, end_time_second_part)

        self.logger.debug("Converted '{0}' to datetime '{1}'".format(start_time,
                                                                     start_time_dt.strftime("%H:%M")))
        self.logger.debug("Converted '{0}' to datetime '{1}'".format(end_time,
                                                                     end_time_dt.strftime("%H:%M")))
        return start_time_dt, end_time_dt

    def convert_time_to_datetime(self, t1):
        """ Given a time, converts it to DateTime object.

        Args:
            t1 (str): time. In the form '12:00 AM'

        Returns:
            t1_dt (datetime.datetime): Start time as a datetime.
        """

        time_first_part, time_second_part, time_ampm_part = self.parse_time(t1)

        if time_ampm_part == "AM":
            if time_first_part == 12:
                t1_dt = datetime.datetime(2016, 1, 1, 0, time_second_part)
            else:
                t1_dt = datetime.datetime(2016, 1, 1, time_first_part, time_second_part)

        else:
            if time_first_part == 12:
                t1_dt = datetime.datetime(2016, 1, 1, 12, time_second_part)
            else:
                t1_dt = datetime.datetime(2016, 1, 1, time_first_part + 12, time_second_part)

        self.logger.debug("Converted '{0}' to datetime '{1}'".format(t1,
                                                                     t1_dt.strftime("%H:%M")))

        return t1_dt

    def convert_datetime_to_time(self, t1):
        """ Given a datetime, converts it to time.

        Args:
            t1 (datetime.datetime): datetime.

        Returns:
            t1_time (str): time. In the form '12:00 AM'
        """

        hour = t1.time().hour
        minute = t1.time().minute

        if hour == 0:
            hour = 12
            ampm = "AM"
        elif hour == 12:
            ampm = "PM"
        elif hour > 12:
            hour -= 12
            ampm = "PM"
        else:
            ampm = "AM"

        if minute < 10:
            converted_time = str(hour) + ":0" + str(minute) + " " + ampm
        else:
            converted_time = str(hour) + ":" + str(minute) + " " + ampm

        self.logger.debug("Converted '{0}' from datetime, '{1}'".format(t1.strftime("%H:%M"),
                                                                        converted_time))

        return converted_time

    def compare_times(self, time_1, time_2):
        """ Given two times, compares them. Times must have come from convert_times_to_datetime

        Args:
            time_1 (datetime.datetime): first time
            time_2 (datetime.datetime): second time

        Returns:
            -1: time_1 is before time_2
            0 : time_1 is the same time as time_2
            1 : time_1 is after time_2
        """

        if time_1 < time_2:
            self.logger.debug("'{0}' is earlier than '{1}'".format(time_1.strftime("%m/%d %H:%M"),
                                                                   time_2.strftime("%m/%d %H:%M")))
            return -1
        elif time_2 < time_1:
            self.logger.debug("'{0}' is later than '{1}'".format(time_1.strftime("%m/%d %H:%M"),
                                                                 time_2.strftime("%m/%d %H:%M")))
            return 1
        else:
            self.logger.debug("'{0}' is the same as '{1}'".format(time_1.strftime("%m/%d %H:%M"),
                                                                  time_2.strftime("%m/%d %H:%M")))
            return 0

    def get_setup_time(self, event_start_time):
        """ Given the event start time, find the setup time based on the delays/advances in settings.json

        Args:
            event_start_time (datetime.datetime): event start time

        Returns:
            setup_time (datetime.datetime): time to setup for event
        """
        if self.compare_times(self.convert_time_to_datetime(
                settings["previous_day_setup_cutoff"]), event_start_time) == 1:
            return datetime.datetime.strptime("2016/1/1 " + settings["setup_time_night_before"], "%Y/%m/%d %I:%M %p")

        time_delta = datetime.timedelta(minutes=settings["minutes_to_advance_setup"])

        return_time = event_start_time - time_delta

        self.logger.info("Setup time is '{}'".format(return_time.strftime("%H:%M")))

        return return_time

    def get_checkin_time(self, event_start_time):
        """ Given the event start time, find the check-in time based on the delays/advances in settings.json

        Args:
            event_start_time (datetime.datetime): event start time

        Returns:
            checkin_time (datetime.datetime): time to check-in event
        """

        time_delta = datetime.timedelta(minutes=settings["minutes_to_advance_checkin"])

        return_time = event_start_time - time_delta

        self.logger.info("Check-in time is '{}'".format(return_time.strftime("%H:%M")))

        return return_time

    def get_teardown_time(self, event_end_time):
        """ Given the event end time, find the teardown time based on the delays/advances in settings.json

        Args:
            event_end_time (datetime.datetime): event end time

        Returns:
            teardown_time (datetime.datetime): time to teardown event
        """

        time_delta = datetime.timedelta(minutes=settings["minutes_to_delay_teardown"])

        return_time = event_end_time + time_delta

        self.logger.info("Teardown time is '{}'".format(return_time.strftime("%H:%M")))

        return return_time

    def select_staff(self, staff):
        """ Selects the person with name 'staff' in the Staff Assignment form

        Args:
            staff (string): name of person to select in format 'Last, First'

        Raises:
            NoSuchElementException: couldn't find that person in the list
        """

        select = Select(self.wait_for_element_visible("#ctl00_ContentPlaceHolder1_ddl_staff"))
        list_of_options = [i.text for i in select.options]
        for option in list_of_options:
            if staff in option:
                select.select_by_index(list_of_options.index(option))
                break
        else:
            staff_list = staff.split(", ")
            truncated_staff = staff_list[0] + ", " + staff_list[1][0:3]
            self.logger.info("Unable to find '{0}' in list of staff, trying '{1}'".format(staff, truncated_staff))
            for option in list_of_options:
                if staff in option:
                    select.select_by_index(list_of_options.index(option))
                    break
            else:
                raise NoSuchElementException("'{}' wasn't found in the list of staff".format(staff))

    def select_assignment(self, assignment):
        """ Selects the assignment 'assignment' in the Staff Assignment form

        Args:
            assignment (string): type of assignment to select

        Raises:
            NoSuchElementException: couldn't find that assignment in the list
        """

        select = Select(self.wait_for_element_visible("#ctl00_ContentPlaceHolder1_ddl_assignments"))
        list_of_options = [i.text for i in select.options]
        for option in list_of_options:
            if assignment in option:
                select.select_by_index(list_of_options.index(option))
                break
        else:
            raise NoSuchElementException("'{}' wasn't found in the list of assignments".format(assignment))

    def enter_time(self, time_to_enter):
        """ Enters the time in the Staff Assignment form.

        Args:
            time_to_enter (string): time to enter in the format "12:00 PM"
        """

        time_split = time_to_enter.split(" ")

        text_box = self.wait_for_element_visible("#ctl00_ContentPlaceHolder1_txt_start_time")
        text_box.clear()
        text_box.send_keys(time_split[0])

        try:
            select = Select(self.wait_for_element_visible("#ctl00_ContentPlaceHolder1_ddl_start_time"))
            select.select_by_visible_text(time_split[1])
        except NoSuchElementException:
            raise NoSuchElementException("'{}' wasn't found in the list of AM/PM".format(time_split[1]))


class W2W:
    """ Contains functions related to WhenToWork """

    def __init__(self, selenium_webdriver, logging):
        self.day = 0
        self.month = 0
        self.year = 0
        self.driver = selenium_webdriver
        self.logger = logging

    def return_day(self):
        return self.day

    def return_month(self):
        return self.month

    def return_year(self):
        return self.year

    def go_to_w2w_with_date(self):
        """ Go to WhenToWork and go to the correct day. Returns the column number corresponding to the correct day

        Returns:
            int: The column number corresponding to the date. Starts at zero.
        """

        # navigate to W2W
        self.driver.get('https://whentowork.com/logins.htm')

        # if not logged in, log in.
        if self.driver.title == "W2W Sign In - WhenToWork Online Employee Scheduling Program":
            input_user = self.driver.find_element_by_name("UserId1")
            input_user.send_keys(settings["w2w_username"])

            input_pass = self.driver.find_element_by_name("Password1")
            input_pass.send_keys(settings["w2w_password"])
            input_pass.submit()

        if self.driver.title == "Sign In - WhenToWork Online Employee Scheduling Program":
            self.logger.exception("Invalid W2W credentials")
            raise RuntimeError("Invalid W2W credentials")

        # navigate to Everyone's Schedule
        self.driver.execute_script("ReplWin('empfullschedule','')")

        # save current window handle
        current_window = self.driver.current_window_handle

        # open date picker and select date
        self.driver.find_element_by_xpath("//*[@id=\"calbtn\"]/nobr/a[4]").click()
        self.driver.switch_to.window(self.driver.window_handles[-1])
        self.driver.execute_script("var y = " + str(year) + "; var m = " + str(month) + "; var d = " + str(day) +
                                   ";if (window.opener.top) {window.opener.top.location=window.opener.top.location+"
                                   "\"&Date=\"+m + \"/\" + d + \"/\" + y;}self.close();")
        self.driver.switch_to.window(current_window)

        # Get correct column number by date
        date_row_xpath = "/html/body/div[4]/table[2]/tbody/tr[2]/td/table/tbody/tr/td/table[1]/tbody/tr"
        date_row = self.driver.find_element_by_xpath(date_row_xpath)
        tds = date_row.find_elements_by_tag_name("td")
        i = 0
        column_num = 0
        for x in tds:
            try:
                x.find_element_by_partial_link_text(name_date)
                column_num = i
                break
            except SeleniumExceptions.NoSuchElementException:
                i += 1

        return column_num

    def go_to_position_type(self, position_name):
        """ Go to the row with position name, 'position_name'

        Args:
            position_name (str): The position name to go to.

        Raises:
            SeleniumExceptions.NoSuchElementException: Unable to find 'position_name' in the list
        """

        select = Select(self.driver.find_element_by_name("EmpListSkill"))
        try:
            self.logger.info("{}:".format(position_name))
            select.select_by_visible_text(position_name)
        except SeleniumExceptions.NoSuchElementException:
            raise SeleniumExceptions.NoSuchElementException("Unable to find '{}' in the list.".format(position_name))

    def parse_w2w_time(self, time_to_parse):
        """ Parse time from WhenToWork. Returns string

        Args:
            time_to_parse (str): The time to parse into form: HH:MM PM

        Returns:
            str: The parsed time

        Raises:
            RuntimeError: Unable to parse time
        """

        if len(time_to_parse.split(":")) == 2:
            dt = datetime.datetime.strptime(time_to_parse, '%I:%M%p')
            returning_str = dt.strftime("%I:%M %p")
            self.logger.debug("Parsed '{0}' to '{1}'".format(time_to_parse, returning_str))
            return returning_str
        elif len(time_to_parse.split(":")) == 1:
            if time_to_parse == " " or "":
                raise RuntimeError("Fatal error: Unable to parse time: is empty")
            dt = datetime.datetime.strptime(time_to_parse, '%I%p')
            returning_str = dt.strftime("%I:%M %p")
            self.logger.debug("Parsed '{0}' to '{1}'".format(time_to_parse, returning_str))
            return returning_str
        else:
            raise RuntimeError("Fatal error: Unable to parse time - '{}'".format(time_to_parse))

    def get_list_of_schedule(self, column_number):
        """ Gets the data from the cell containing the schedule for the given day. Requires that W2W is already filtered to
            the desired position

        Args:
            column_number (int): The column number corresponding to the required date.

        Returns:
            [{}]: List of dicts with the time and person in the schedule.
                Keys:
                    "last_name"
                    "first_name"
                    "start_time"
                    "end_time"
        """

        data_row_xpath = "/html/body/div[4]/table[2]/tbody/tr[2]/td/table/tbody/tr/td/table[2]/tbody/tr"
        list_of_rows = self.driver.find_elements_by_xpath(data_row_xpath)
        list_of_cells = list_of_rows[1].find_elements_by_tag_name("td")
        cell = list_of_cells[column_number]

        raw_list = cell.text.split("\n")
        paired_times = []
        i = 0

        if len(raw_list) > 1:
            while i < len(raw_list):
                if raw_list[i][:2] == "  ":
                    i += 1
                else:
                    # parse time
                    time_list = raw_list[i].split(" - ")
                    start_datetime = self.parse_w2w_time(time_list[0])
                    end_datetime = self.parse_w2w_time(time_list[1])

                    # parse name
                    name_list = raw_list[i + 1].split(" ")
                    first_name = name_list[2]  # first two spaces are empty
                    if first_name != "(Unassigned)":
                        last_name = name_list[3]

                        position_dict = {
                            "last_name": last_name,
                            "first_name": first_name,
                            "start_time": start_datetime,
                            "end_time": end_datetime,
                        }
                        self.logger.info(" - '{0} {1}' @ '{2}' - '{3}'".format(first_name,
                                                                               last_name,
                                                                               start_datetime,
                                                                               end_datetime))
                        paired_times.append(position_dict)

                    i += 2
        return paired_times


def setup():
    """ Sets up environment for entire program.
         - Set up logging
         - Clears the screen
         - Checks for settings.json file
         - Imports settings.json file
         - Validates json file
    """

    logger.basicConfig(format='%(asctime)s %(levelname)s:%(message)s',
                       filename='debug_log.log',
                       level=logger.INFO,
                       datefmt='%m/%d/%Y %I:%M:%S %p')
    logger.getLogger().addHandler(logger.StreamHandler())
    selenium_logger = logger.getLogger('selenium.webdriver.remote.remote_connection')
    # Only display possible problems
    selenium_logger.setLevel(logger.WARNING)

    logger.info("******************* Running Autofill Tool *******************")

    # check platform, clear screen
    platform = sys.platform

    if platform == "win32":
        os.system('cls')
    elif platform in ["darwin", "linux", "darwin"]:
        os.system('clear')
    else:
        raise RuntimeError("Platform '{}' not supported".format(platform))

    # check settings files exist
    if not os.path.isfile('settings.json'):
        raise RuntimeError("settings.json doesn't exist in path '{}'".format(os.getcwd()))

    # open settings file
    logger.info("Reading settings file")
    try:
        with open('settings.json', 'r') as settings_file:
            settings_json = settings_file.read()
            global settings
            settings = json.loads(settings_json)
            settings_file.close()
    except RuntimeError:
        raise RuntimeError("Error reading settings.json.")


def get_date():
    """ Gets the date, ensures it's a valid date, asks for confirmation, and returns the parsed date. Requires
        date is in 'M/D/YYYY' format.

   Return:
       str: String date, in the form of 'Jan-1"
       int: Year, in form 'YYYY'
       int: Month, in form 'M'
       int: Day, in form 'D'

    """

    # prompt date
    valid_date = 0
    input_month = 0
    input_day = 0
    input_year = 0
    tomorrow = datetime.datetime.now() + datetime.timedelta(days=1)

    if settings["custom_date"] is False:
        date_list = tomorrow.strftime("%m/%d/%Y").split("/")
        input_month = int(date_list[0])
        input_day = int(date_list[1])
        input_year = int(date_list[2])
    else:
        while not valid_date:
            try:
                print("Enter date (eg {0} = \"{1}\").".format(tomorrow.strftime("%B %d %Y"), tomorrow.strftime("%m/%d/%Y")))
                input_date = input("Press enter to use {}: ".format(tomorrow.strftime("%B %d %Y")))

                if input_date != "":
                    # parse date
                    date_list = input_date.split("/")
                    input_month = int(date_list[0])
                    input_day = int(date_list[1])
                    input_year = int(date_list[2])
                    if input_month < 1 or input_month > 12:
                        print("Invalid month: {}".format(input_month))
                    elif input_day < 1 or input_day > 31:
                        print("Invalid day: {}".format(input_day))
                    elif input_year < 0 or input_year > 2099 or 99 < input_year < 2000:
                        print("Invalid year: {}".format(input_year))
                    else:
                        # if two digit year, convert to 4 digit year.
                        if input_year < 2000:
                            input_year += 2000
                        valid_date = 1
                else:
                    input_month = tomorrow.month
                    input_day = tomorrow.day
                    input_year = tomorrow.year
                    valid_date = 1

            except (RuntimeError, ValueError):
                print("Invalid date entry")

    if input_month == 1:
        name_month = "Jan"
    elif input_month == 2:
        name_month = "Feb"
    elif input_month == 3:
        name_month = "Mar"
    elif input_month == 4:
        name_month = "Apr"
    elif input_month == 5:
        name_month = "May"
    elif input_month == 6:
        name_month = "Jun"
    elif input_month == 7:
        name_month = "Jul"
    elif input_month == 8:
        name_month = "Aug"
    elif input_month == 9:
        name_month = "Sep"
    elif input_month == 10:
        name_month = "Oct"
    elif input_month == 11:
        name_month = "Nov"
    elif input_month == 12:
        name_month = "Dec"
    else:
        raise RuntimeError("Unknown input month. Error parsing? '{}'".format(input_month))

    return str(name_month) + "-" + str(input_day), input_year, input_month, input_day


def parse_schedule_file(log):
    """ Parses schedule.json file. Only runs if settings["use_w2w"] is False

    Args:
        log (logging): logger object

    Returns:
        dict: schedule file
    """

    # Check schedule.json exists
    log.debug("Checking schedule file exists")
    if not os.path.isfile('schedule.json'):
        raise RuntimeError("schedule.json doesn't exist in path '{}'".format(os.getcwd()))

    # open schedule file
    log.debug("Reading schedule file")
    try:
        with open('schedule.json', 'r') as schedule_file:
            schedule_json = schedule_file.read()
            schedule_dict = json.loads(schedule_json)
            schedule_file.close()
    except RuntimeError:
        raise RuntimeError("There was an error with schedule.json")

    return schedule_dict


# Get the web driver
driver = webdriver.Chrome()

try:
    # Setup environment
    setup()

    # get date information
    name_date, year, month, day = get_date()

    schedule = {}

    if settings["use_w2w"] is True:
        # create W2W object
        w2w = W2W(driver, logger)

        # go to w2w and load schedule
        col_num = w2w.go_to_w2w_with_date()
        for position in settings["order_to_assign_general_shift"]:
            w2w.go_to_position_type(position)
            parsed_list = w2w.get_list_of_schedule(col_num)
            schedule[position] = parsed_list
    else:
        schedule = parse_schedule_file(logger)

    ems = EMS(driver, logger, schedule, year, month, day)

    # get list of events
    list_of_events = ems.get_list_of_events()

    # get list of javascript commands
    list_of_javascript = ems.get_list_of_javascript(list_of_events)

    # go to event and schedule
    redo = False
    for command in list_of_javascript:
        redo = ems.schedule_event(command)
        if redo is None:
            redo = False
        else:
            ems.navigate_to_event_listing_page(select_position=False)
            redo = True
            break

    # if need to redo, refresh JS list and continue.
    while redo is True:
        list_of_events = ems.get_list_of_events()
        list_of_javascript = ems.get_list_of_javascript(list_of_events)
        for command in list_of_javascript:
            redo = ems.schedule_event(command)
            if redo is None:
                redo = False
            else:
                ems.navigate_to_event_listing_page(select_position=False)
                redo = True
                break

finally:
    driver.quit()



