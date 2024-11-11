from habanero import Crossref 
import pandas as pd

# Initialize Crossref API
cr = Crossref()

# Load the Excel file
data = pd.read_excel('Medrxiv_Data.xlsx')  # Update with your file path if needed
publicationType = 'Prepint'
source = 'medRxiv'
# Function to extract the DOI part without version suffix
def extract_doi(url):
    # Split the URL to get the part after '/content/'
    doi_part = url.split('/content/')[1]
    # Remove the version suffix if it exists (e.g., "v1" or "v2")
    doi_cleaned = doi_part.split('v')[0]
    return doi_cleaned

# Apply the function to the 'DOI' column
data['DOI_Extracted'] = data['DOI'].apply(extract_doi)

# List to store filtered data
data_filtered = []

# Counter to track progress
count = 0

# Loop over each DOI and retrieve data from Crossref
for doi in data['DOI_Extracted']:
    try:
        # Get work data from Crossref for the current DOI
        result = cr.works(ids=doi)
        count += 1

        # Extract relevant information if available
        doi_info = result['message']
        doi_number = doi_info.get('DOI', None)
        doi_name = doi_info.get('title', [None])[0]
        authors = [
            f"{author.get('given', 'Unknown')} {author.get('family', 'Unknown')}"
            for author in result["message"].get("author", [])
        ]
        joinAuthors = ", ".join(authors)
        authorsCleaned = joinAuthors.replace("[", "").replace("]", "").replace("'", "")
 
        # Extract published date if available
        published_date_parts = doi_info.get('published', {}).get('date-parts', [[None, None, None]])[0]
        doi_published_date = f"{published_date_parts[0]}-{published_date_parts[1]:02d}-{published_date_parts[2]:02d}" if published_date_parts[0] else None

        referenced_count = doi_info.get('is-referenced-by-count', None)
        url = doi_info.get('resource',{}).get('primary',{}).get('URL',None)
        relation = doi_info.get('relation', None)
        
        # Initialize secondary article variables as None
        doi2, doi_name2, doi_published_date2, referenced_count2 = None, None, None, None

        # Check if the relation field is not empty and fetch secondary DOI details
        if 'is-preprint-of' in relation:
            doi2 = relation['is-preprint-of'][0].get('id')
            if doi2:
                result2 = cr.works(ids=doi2)
                doi_info2 = result2['message']
                doi_name2 = doi_info2.get('title', [None])[0]
                
                # Extract secondary published date if available
                published_date_parts2 = doi_info2.get('created', {}).get('date-parts', [[None, None, None]])[0]
                doi_published_date2 = f"{published_date_parts2[0]}-{published_date_parts2[1]:02d}-{published_date_parts2[2]:02d}" if published_date_parts2[0] else None
                referenced_count2 = doi_info2.get('is-referenced-by-count', None)

        # Append the extracted data to data_filtered list
        data_filtered.append([
            count,doi_number, doi_name, authorsCleaned, publicationType, source, url, referenced_count, doi_published_date, 
            relation, doi2, doi_name2, referenced_count2, doi_published_date2
        ])
        
        # Increment the counter and print progress
        print(f"Processed {count} articles")

    except Exception as e:
        print(f"Error processing DOI {doi}: {e}")
        # Append DOI with None values for articles with errors
        data_filtered.append([doi, None, None, None, None, None, None, None, None])

# Convert the list to a DataFrame and save to Excel
df = pd.DataFrame(data_filtered, columns=[
    'Number','DOI', 'Title', 'Authors','Publication Type','Source','URL','Referenced By Count', 'Published Date', 'Relation', 
    'DOI 2 Published', 'Title 2 Published', 'Referenced By Count 2 Published', 'Created Date'
])
df.to_excel('./Crossref_Data.xlsx', index=False)
print("Data saved to Crossref_Data.xlsx")
