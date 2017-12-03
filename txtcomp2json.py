#!/usr/bin/env python
# -*- coding: utf-8 -*-

# November 2017. OEDO Analytics Group
#
# The program processes html data and produces .json output:
# all text components -> all_textcomp.json
# all problem components -> all_probcomp.json
# all video components -> all_videocomp.json
# all components (text, problems, videos) -> all_comp.json

#===============================================================


import os,re,json
import codecs

from bs4 import BeautifulSoup as BeautifulSoup
from nltk.stem import PorterStemmer
from nltk.tokenize import sent_tokenize, word_tokenize
from collections import Counter 

BASE_PATH = 'HTMLs'

def course_selection():
    
    courses = os.listdir(BASE_PATH)  
    idxs_ls = []
    course_ls = []
    print ('list of downloaded courses')
    for idx,course in enumerate(courses):
        course_ls.append(course)
        idxs_ls.append(str(idx+1))
        print (str(idx+1) +' : ' + course)
    flag = 0
    while flag == 0:
        chosen_course_id = input('enter course number ')
        if chosen_course_id in idxs_ls:
            flag = 1
            chosen_course = course_ls[int(chosen_course_id)-1]
            print (chosen_course + '\n')
        else:
            print ('wrong course id. Try again!!!!!!!!')
    return chosen_course


def check_true_dir(selected_dir):
    if os.path.isdir(selected_dir):
        return os.listdir(selected_dir) 
    else:
        return []


def winapi_path(dos_path, encoding=None):
    if (not isinstance(dos_path, unicode) and 
        encoding is not None):
        dos_path = dos_path.decode(encoding)
    path = os.path.abspath(dos_path)
    if path.startswith(u"\\\\"):
        return u"\\\\?\\UNC\\" + path[2:]
    return u"\\\\?\\" + path


def file2dict(chosen_course):
 
    txt_id = 1
    prob_id = 1
    video_id =  1
    comp_id = 1
    txt_all = ""
    txt_dict_ls = dict()
    prob_dict_ls = dict()
    comp_dict_ls = dict()
    video_dict_ls = dict()
    chosen_course_dir = os.path.join(BASE_PATH,chosen_course)
    sections_ls = check_true_dir(chosen_course_dir)
    for section in sections_ls:
        subsections_ls =  check_true_dir(os.path.join(chosen_course_dir,section))
        for subsection in subsections_ls:
            comp_ls = check_true_dir(os.path.join(chosen_course_dir,section,subsection))
            for comp_file in comp_ls:
                pattern_txt_comp = re.compile(".*\d.txt")
                pattern_prob_comp = re.compile(".*\d_prob.txt")
                pattern_comp = re.compile(".*\d.html")
                pattern_video = re.compile(".*vdo.json")

                if pattern_txt_comp.match(comp_file):
                    file = open(os.path.join(chosen_course_dir,section,subsection,comp_file),'r',encoding='utf-8')
                    txt_contents = file.read()
                    txt_all += txt_contents+"\n"
                    tmp_dict = {'text_block_'+str(txt_id).zfill(2):{'section': section , 'subsection': subsection, 'unit_idx': comp_file, 'word_count': str(len(txt_contents.split())),'content':txt_contents}}
                    txt_dict_ls.update(tmp_dict)
                    file.close()
                    #print(tmp_dict)
                    txt_id +=1
                elif pattern_prob_comp.match(comp_file):
                    file = open(os.path.join(chosen_course_dir,section,subsection,comp_file),'r',encoding='utf-8')
                    txt_contents = file.read()
                    txt_all += txt_contents+"\n"
                    tmp_dict = {'quiz_block_'+str(prob_id).zfill(2):{'section': section , 'subsection': subsection, 'unit_idx': comp_file, 'word_count': str(len(txt_contents.split())),'content':txt_contents}}
                    prob_dict_ls.update(tmp_dict)
                    file.close()
                    #print(tmp_dict)
                    prob_id +=1
                elif pattern_video.match(comp_file):
                    file = open(os.path.join(chosen_course_dir,section,subsection,comp_file),'r',encoding='utf-8')
                    txt_contents = file.read()
                    video_dict = json.loads(txt_contents)
                    for main_key, main_value in video_dict.items():
                        for key, value in main_value.items():
                            #print(type(value))
                            if type(value) is list:   
                                video_dict[main_key][key] = ' '.join(video_dict[main_key][key])

                    video_dict_ls.update(video_dict)
                    file.close()
                    video_id +=1
                elif pattern_comp.match(comp_file):
                    file = open(os.path.join(chosen_course_dir,section,subsection,comp_file),'r',encoding='utf-8')
                    soup = BeautifulSoup(file,'html.parser')
                    set_comp_types = soup.findAll("div", {"data-type":True})
                    for comp_type in set_comp_types:
                        comp_dict = {str(comp_id).zfill(2)+'_'+comp_type['data-type']:{'section': section , 'subsection': subsection, 'unit_idx': comp_file, 'type': comp_type['data-block-type']}}
                        comp_dict_ls.update(comp_dict)
                        comp_id+=1
                    file.close()
                

    txt_dict2json = json.dumps(txt_dict_ls, sort_keys=True, indent=4, separators=(',', ': '))
    f = open(os.path.join(chosen_course_dir,'all_textcomp.json'),'w',encoding='utf-8')
    f.write(txt_dict2json)
    

    prob_dict2json = json.dumps(prob_dict_ls, sort_keys=True, indent=4, separators=(',', ': '))
    f = open(os.path.join(chosen_course_dir,'all_probcomp.json'),'w',encoding='utf-8')
    f.write(prob_dict2json)

    video_dict2json = json.dumps(video_dict_ls, sort_keys=True, indent=4, separators=(',', ': '))
    f = open(os.path.join(chosen_course_dir,'all_videocomp.json'),'w',encoding='utf-8')
    f.write(video_dict2json)

    comp_dict2json = json.dumps(comp_dict_ls, sort_keys=True, indent=4, separators=(',', ': '))
    f = open(os.path.join(chosen_course_dir,'all_comp.json'),'w',encoding='utf-8')
    f.write(comp_dict2json)


    
    ## write all text into 1 file
    file_txt = codecs.open(os.path.join(BASE_PATH, chosen_course,"all_text.txt"), 'w', 'utf-8')    
    file_txt.writelines(txt_all)
    file_txt.close()

    #count all word
    corpus = ""
    word_array = txt_all.split()
    #using porter stemmer
    ps = PorterStemmer()
    stemming_array = []
    for w in word_array:
        w = re.sub('[.,!?(){}\'\";:]', '', w)
        stemming_array.append(ps.stem(w))
        
    word_count = Counter(stemming_array)
    for value, count in word_count.most_common():
        #print(value, count)
        corpus+=value+"\t"+str(count)+"\n"
    #### create file
    file_txt = codecs.open(os.path.join(BASE_PATH, chosen_course,"corpus.txt"), 'w', 'utf-8')   
    file_txt.writelines(corpus)
    file_txt.close()


def main(): 
    file2dict(course_selection())


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logging.warn("\n\nCTRL-C detected, shutting down....")
        sys.exit(ExitCode.OK)
    