import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException

import time

# Set up Chrome options
chrome_options = Options()
chrome_options.add_argument("--headless")  # Run in headless mode if preferred
service = Service('/home/josecxz/QuantumSpace/chromedriver-linux64/chromedriver-linux64/chromedriver')  
# Setup Selenium with Chrome WebDriver
driver = webdriver.Chrome(options=chrome_options)

# Data storage
data = []
article_count = 0

# Function to get titles and DOIs from a single page
def get_titles_and_dois():
    global article_count
    titles = driver.find_elements(By.CSS_SELECTOR, "a.article-title")
    # Check if there are titles before processing
    if not titles:
        print("No titles found on the page.")
        return

    for index in range(len(titles)):
        try:
            if index < len(titles):  # Ensure the index is within bounds
                title = titles[index]
                article_title = title.text
                article_link = title.get_attribute('href')
                print(f"Title: {article_title}")

                # Click on the article link to retrieve DOI
                driver.get(article_link)
                time.sleep(5)  # Wait for the article page to load

                # Locate and extract the DOI
                doi_element = driver.find_element(By.XPATH, "//p[contains(text(), 'https://doi.org')]")
                doi = doi_element.text
                print(f"DOI: {doi}")

                # Append data to list
                data.append({"Title": article_title, "DOI": doi})

                # Increment the counter and print progress
                article_count += 1
                print(f"Processed {article_count} articles")
            else:
                print("Index out of range for titles list")
        except Exception as e:
            print("Error:", e)
        finally:
            # Go back to the main page and wait for it to load
            driver.back()
            time.sleep(5)  # Wait for the main page to reload
            # Re-fetch titles after going back
            titles = driver.find_elements(By.CSS_SELECTOR, "a.article-title")
            if not titles:  # Check if titles exist after going back
                print("No titles found after going back. Exiting...")
                return  # Exit if no titles are found

# Function to navigate through all pages
def navigate_pages():
    while True:
        get_titles_and_dois()
        try:
            # Locate and click the "Next" button
            next_button = driver.find_element(By.CSS_SELECTOR, "li a.pagination-link[aria-label='Go to next page']")
            driver.execute_script("arguments[0].click();", next_button)
            time.sleep(5)  # Wait for the next page to load
        except NoSuchElementException:
            print("Reached the last page or no more pages available.")
            break

# Open the initial webpage
url = "https://www.researchsquare.com/browse?offset=0&status=all&subjectArea=Cardiac%20%26%20Cardiovascular%20Systems"
driver.get(url)
time.sleep(5)  # Allow time for dynamic content to load

# Start navigating through all pages
navigate_pages()

# Save data to Excel
df = pd.DataFrame(data)
df.to_excel("research_articles.xlsx", index=False)

driver.quit()
