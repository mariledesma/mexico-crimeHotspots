"""Count conservation and missing-data safeguards for population extraction."""
import unittest
import numpy as np
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from shapely import transform
from shapely.geometry import box
from shapely.strtree import STRtree
from population import summarize, weighted_population
from spatial import TO_METERS

class PopulationTests(unittest.TestCase):
    def test_count_conservation_and_partial_overlap(self):
        cells=[box(0,0,10,10),box(10,0,20,10)]
        counts=np.array([100.,200.]);tree=STRtree(cells)
        self.assertAlmostEqual(summarize(box(0,0,20,10),cells,counts,tree),300.)
        self.assertAlmostEqual(summarize(box(5,0,15,10),cells,counts,tree),150.)
        with self.assertRaises(ValueError):
            summarize(box(-1,0,20,10),cells,counts,tree)

    def test_missing_population_is_not_zero(self):
        geographic=box(-99.14,19.42,-99.13,19.43)
        polygon=transform(geographic,TO_METERS.transform,interleaved=False)
        with MemoryFile() as memory:
            with memory.open(driver='GTiff',height=1,width=1,count=1,dtype='float32',crs='EPSG:4326',transform=from_origin(-99.14,19.43,.01,.01),nodata=-99999) as dataset:
                dataset.write(np.array([[-99999]],dtype='float32'),1)
                with self.assertRaises(ValueError):
                    weighted_population(dataset,polygon)
                dataset.write(np.array([[0]],dtype='float32'),1)
                cells,counts,tree=weighted_population(dataset,polygon)
                self.assertAlmostEqual(summarize(polygon,cells,counts,tree),0.)

if __name__=='__main__':
    unittest.main()
