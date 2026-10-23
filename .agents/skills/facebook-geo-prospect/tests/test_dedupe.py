import csv
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from dedupe import run,fbkey,domain

class TestDedupe(unittest.TestCase):
    def test_fb_profile_normalization(self):
        self.assertEqual(fbkey('https://m.facebook.com/profile.php?id=123&utm=4'),'id:123')
        self.assertEqual(fbkey('https://www.facebook.com/SomeBrand/'),'somebrand')
    def test_domain(self):
        self.assertEqual(domain('https://www.Example.com/about'),'example.com')
    def test_cross_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            t=Path(tmp)
            def csvfile(n,rows):
                p=t/n
                with open(p,'w',encoding='utf-8',newline='') as f:
                    w=csv.DictWriter(f,fieldnames=['company','website','fb_profile_url']);w.writeheader();w.writerows(rows)
                return p
            h=csvfile('old.csv',[{'company':'Some Company','website':'https://www.somecompany.com','fb_profile_url':'https://facebook.com/somecompany'}, {'company':'Aardvark Digital','website':'https://aardvark.io','fb_profile_url':''}])
            c=csvfile('new.csv',[{'company':'SOME COMPANY','website':'','fb_profile_url':''},{'company':'Unknown Co','website':'https://somecompany.com/','fb_profile_url':''},{'company':'Other','website':'','fb_profile_url':'https://m.facebook.com/somecompany/'},{'company':'Unique Co','website':'https://unique.com','fb_profile_url':''}])
            o=t/'results.csv';run(c,[h],o)
            with open(o,encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
            self.assertEqual([r['_dedupe_status'] for r in rows],['MATCH_HISTORY','MATCH_HISTORY','MATCH_HISTORY','NO_HISTORY_MATCH_FOUND'])

if __name__=='__main__': unittest.main()
