from undetected_geckodriver import Firefox
import os
import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

import random, time 

print(f"runner ip: {requests.get('https://api.ipify.org/').text}")


import getpass

try:
    os.getlogin()
except OSError:
    def getlogin_monkey_patch():
        return getpass.getuser()

    os.getlogin = getlogin_monkey_patch



def generate_random_birthdate():
    month = random.choice(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])
    day = random.choice(range(1, 27))
    year = str(random.randint(1995, 2002))
    return month, day, year

PASSWORD = "Glibbertyglobbersmelledafogger!"
upload_key = os.getenv("UPLOAD_KEY")

firstnames = ["sang", "prefer", "shownape", "caet", "spec", "bug", "baggie", "smith", "doraldo", "ches", "john", "james", "frog", "miller", "aust", "cluster", "john"] # heh..
middlenames = ["swag", "isawesome", "isnice", "isamazing", "smells", "ismean", "isokay", "mid", "derp", "sweg", "toilet", "admin", "packet", "cube"]
lastnames = ["itius", "inion", "ion", "ian","xd", "xD", "ii", "th", "v", "rum", "cache"]

def generate_username():
    return random.choice(firstnames) + random.choice(middlenames) + random.choice(lastnames) + str(random.randint(1, 999))
        

def random_sleep(min = 0.3, max = 0.8):
    time.sleep(random.uniform(min, max))

def fill_out_page(driver):
    month, day, year = generate_random_birthdate()
    print(f"Generated birthdate: {month} {day}, {year}") # Debug print

    month_select = Select(driver.find_element(By.ID, "MonthDropdown"))
    month_select.select_by_value(month)
    print(f"Selected month: {month}") # Debug print

    day_select = Select(driver.find_element(By.ID, "DayDropdown"))
    day_select.select_by_value(f"{day:02d}")
    print(f"Selected day: {day}") # Debug print

    year_select = Select(driver.find_element(By.ID, "YearDropdown"))
    year_select.select_by_value(year)
    print(f"Selected year: {year}") # Debug print

    username_input = driver.find_element(By.ID, "signup-username")
    
    while True:
        username = generate_username()
        username_input.send_keys(username)
        print(f"Attempting username: {username}") # Debug print
       # driver.execute_script("arguments[0].blur();", username_input)
        random_sleep()
        
        try:
            success_div = driver.find_element(By.XPATH, "//div[contains(@class, 'has-success') and input[@id='signup-username']]")
            if success_div:
                print(f"Username {username} accepted.") # Debug print
                break
        except:
            pass
        
        try:
            error_div = driver.find_element(By.XPATH, "//div[contains(@class, 'has-error') and input[@id='signup-username']]")
            if error_div:
                print(f"Username {username} rejected, trying again.") # Debug print
                username_input.send_keys(Keys.CONTROL + "a")
                username_input.send_keys(Keys.DELETE) # different way same result - miller
        except:
            pass
    random_sleep()

    password_input = driver.find_element(By.ID, "signup-password")
    password_input.send_keys(PASSWORD)
    print("Password entered.") # Debug print
    random_sleep()

    try:
        signup_checkbox = driver.find_element(By.ID, "signup-checkbox")
        if signup_checkbox:
            signup_checkbox.click()
            random_sleep()
    except Exception as e:
        print("Signup checkbox doesnt exist")

    signup_button = driver.find_element(By.ID, "signup-button")

    signup_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "signup-button")))
    signup_button.click()
    random_sleep()

    print("Signup button clicked.") 

def kill_account_protection(drv):
    try:
        drv.get("https://create.roblox.com/settings/advanced")
        print("Accessed account protection settings page.") # Debug print
        wait = WebDriverWait(drv, 30)

        unprotected_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-testid='unprotected-button']")))
        unprotected_btn.click()
        print("Clicked 'Unprotected' button.") 
        random_sleep(1.4, 2) 

        checkbox_label = wait.until(EC.element_to_be_clickable((By.XPATH, "/html/body/div[2]/div[3]/div/div[1]/span/div[2]/label")))
        checkbox_label.click() 
        print("Clicked checkbox.") 
        random_sleep()

        disable_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-testid='disable-button']")))
        disable_btn.click()
        print("Clicked 'Disable' button.") 
        time.sleep(5) # wait just in case if pop up

        drv.switch_to.frame("challenge-frame")

        password_input_box = wait.until(EC.presence_of_element_located((By.ID, "two-step-verification-code-input")))  
        password_input_box.send_keys(PASSWORD) 
        random_sleep(.5, 1.2)

        verify_button = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'button.btn-cta-md.modal-modern-footer-button[aria-label="Verify"]')))   
        verify_button.click()
  
        drv.switch_to.default_content()

        time.sleep(3)


    except Exception as e:
        print("settings step failed:", e)
        return False # solution: kill yourself - miller

    print("Account protection successfully killed.") # Debug print
    return True

def main():
    driver = Firefox()
    #driver.maximize_window()
        
    try:
        print("Browser initialized.") # Debug print
        driver.get("https://www.roblox.com/CreateAccount")
        print("Accessed Roblox account creation page.") # Debug print

        fill_out_page(driver)

        while True: 
            if "https://www.roblox.com/home" in driver.current_url: 
                break

            try:
                driver.find_element(By.CSS_SELECTOR, 'iframe[title="Verification challenge"], iframe[src*="arkoselabs"]')
                print("Detected captcha, done.")
                driver.quit()
                exit()
            except Exception:
                pass

            try:
                driver.find_element(By.CSS_SELECTOR, 'div#GeneralErrorText[role="button"][aria-label="dismiss general error"]')
                print("Detected general error, quitting.")
                driver.quit()
                exit()
            except Exception:
                pass

        success = kill_account_protection(driver)

        if success:
            roblosecurity_cookie = driver.get_cookie('.ROBLOSECURITY')
            
            response = requests.post(
                "http://pi.bug.tools:4200/api/upload_created_cookie",
                json={
                    "Cookie": roblosecurity_cookie["value"]
                },
                headers={
                    "x-api-key": upload_key
                }
            )

            if response.status_code == 200:
                print("Cookie uploaded successfully.")
            else:
                print(f"Failed to upload cookie: {response.status_code} - {response.text}")
        else:
            driver.quit() 
            main()
            return
    finally:
        try:
            driver.quit()
        except:
            print("program closed, but webdriver already shutdown")

while True: 
    try: 
        main()
    except KeyboardInterrupt:
        exit()
