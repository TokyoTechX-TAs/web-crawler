import os
import re
import csv
import pandas as pd
import urllib.parse


def crawl(category):

	file_name=category+".csv"
	links=[]

	df = pd.read_csv(file_name)
	links = df.URL #you can also use df['column_name']
	#print ("Number of courses in csv: ",len(links))

	user=""
	passwd=""

	query="python edx_crawler.py -u " + user +"  -p "+passwd+" -url "
	for link in links:
		link=link.strip('\n')
		link=urllib.parse.unquote(link,encoding='utf-8', errors='replace')
		query=query+" "+link
	
	#print ("<"+query+">")	
	try:
		os.system(query)
	except Exception as e:
		print(e)
			

def main():
	#categs=["Business & Management"]
	#categs=["Business & Management", "Computer Science", "Humanities"]

	categs=["Engineering", "Math", "Physics", "Social Sciences"]
	for c in categs:
		print (c)
		crawl(c)


if __name__== "__main__":
	main()		
