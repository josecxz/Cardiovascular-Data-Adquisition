import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time

# Set up Chrome options
chrome_options = Options()
chrome_options.add_argument("--headless")  # Run in headless mode if preferred
service = Service('/home/josecxz/QuantumSpace/chromedriver-linux64/chromedriver-linux64/chromedriver')  # Update with your chromedriver path

# Start WebDriver
driver = webdriver.Chrome(service=service, options=chrome_options)

# Open the webpage
driver.get("https://www.medrxiv.org/collection/cardiovascular-medicine")

# Prepare lists to store the data
titles = []
dois = []

# Wait for the elements to load and scrape data
try:
    while True:
        # Wait until elements with DOI links are present
        publications = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.XPATH, "//a[contains(@href, '/content/10.1101/')]"))
        )

        # Extract DOIs and titles
        for pub in publications:
            doi = pub.get_attribute("href")
            title = pub.text  # Gets the title text of the publication
            titles.append(title)
            dois.append(doi)
        print(dois)
        # Attempt to find the "Next" button
        try:
            next_button = WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.LINK_TEXT, "Next"))
            )
            driver.execute_script("arguments[0].click();", next_button)  # Click the "Next" button
            print("Navigated to:", driver.current_url)
            time.sleep(2)  # Wait for the page to load after clicking
        except Exception:
            print("Reached the last page or the 'Next' button is not available.")
            break  # Exit loop when "Next" button is no longer available

except Exception as e:
    print("Error:", e)

finally:
    # Close WebDriver
    driver.quit()

# Create a DataFrame and save to CSV or Excel
data = pd.DataFrame({'Title': titles, 'DOI': dois})
data.to_csv('publications.csv', index=False)   # Save to CSV
data.to_excel('publications.xlsx', index=False)  # Save to Excel

print("Data saved to publications.csv and publications.xlsx")
