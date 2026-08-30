import pandas as pd

df = pd.read_csv('sales.csv')

df['date'] = pd.to_datetime(df['date'])

df['month'] = df['date'].dt.month

df['year'] = df['date'].dt.year

df_monthly_sales = df.groupby(['year', 'month'])['sales'].sum().reset_index()

print(df_monthly_sales)