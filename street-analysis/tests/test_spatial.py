import math,unittest
import numpy as np
from spatial import intensity,mine_patterns,mine_context

class SpatialTests(unittest.TestCase):
    def test_kde_counts_and_duration(self):
        one=1e6/(2*math.pi*100**2)
        self.assertAlmostEqual(intensity([[0,0]],[[0,0]],100)[0],one)
        self.assertAlmostEqual(intensity([[0,0],[0,0]],[[0,0]],100,60)[0],one)
        self.assertEqual(intensity([],[[0,0]],100)[0],0)
    def test_distinct_participants_and_time_window(self):
        r=mine_patterns([[0,0],[1,0],[0,1],[100,100]],['A','A','B','B'],['one']*4,radius=2,threshold=.1)
        self.assertEqual(r['patterns'][0]['participation'],{'A':1,'B':.5})
        self.assertEqual(r['patterns'][0]['pi'],.5)
        self.assertFalse(mine_patterns([[0,0],[0,0]],['A','B'],['Jan','Feb'],radius=2)['patterns'])
    def test_triple_must_be_clique(self):
        x=[[0,0],[.7,0],[1.4,0],[10,0],[10.7,0]];t=['A','B','C','A','C'];g=['m']*5
        r=mine_patterns(x,t,g,radius=1,threshold=.5)
        self.assertEqual(len(r['patterns']),3)
        self.assertEqual(r['stats']['triple_candidates'],1)
        self.assertTrue(all(p['size']==2 for p in r['patterns']))
    def test_grid_matches_baseline_and_prunes(self):
        rng=np.random.default_rng(9);xy=rng.uniform(0,1500,(160,2));labels=rng.choice(list('ABCD'),160).tolist();groups=rng.choice(['Jan','Feb'],160).tolist()
        a=mine_patterns(xy,labels,groups,radius=150,threshold=.14,method='baseline');b=mine_patterns(xy,labels,groups,radius=150,threshold=.14)
        self.assertEqual(a['patterns'],b['patterns']);self.assertLess(b['stats']['distance_checks'],a['stats']['distance_checks'])
    def test_context_counts_unique_places(self):
        r=mine_context([[0,0],[1,1],[1000,1000]],['A','A','B'],['m']*3,[[0,0],[300,300]],['Bank','Bank'],10,.1,19)
        self.assertEqual(r['patterns'][0]['participation'],{'A':1.,'Place: Bank':.5})
        self.assertGreaterEqual(r['patterns'][0]['q_value'],r['patterns'][0]['p_value'])

if __name__=='__main__':unittest.main()
