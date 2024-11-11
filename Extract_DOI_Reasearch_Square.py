import pandas as pd

# Load the Excel file
df = pd.read_excel('research_articles.xlsx')

# Assuming the column with DOI info is named 'DOI'
# Remove the 'https://doi.org/' prefix from each entry
df['extracted_doi'] = df['DOI'].str.replace('https://doi.org/', '', regex=False)

# Save the result to a new Excel file
df.to_excel('Research_Square_Data.xlsx', index=False)

# Display the first few rows to verify
print(df.head())
