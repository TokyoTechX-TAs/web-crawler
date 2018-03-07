import os

file_name="links.txt"

with open(file_name) as f:
    content = f.readlines()
links = [x.strip() for x in content] 

user=""
passwd=""

string="python edx_crawler.py -u " + user +"  -p "+passwd+" -url "
for link in links:
	os.system(string+" " +link)