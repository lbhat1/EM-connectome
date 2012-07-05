from collections import defaultdict
import argparse
import sys
import os
import numpy as np
import urllib, urllib2
import cStringIO

import empaths
import annproj
import anndb
import dbconfig
import zindex


"""Build an index for an existing annotation Dtabase"""

class CreateIndex:
  """Stack of annotations."""

  def __init__(self, token):
    """Load the annotation database and project"""

    annprojdb = annproj.AnnotateProjectsDB()
    self.annoproj = annprojdb.getAnnoProj ( token )
    self.dbcfg = dbconfig.switchDataset ( self.annoproj.getDataset() )

    # Bind the annotation database
    self.annoDB = anndb.AnnotateDB ( self.dbcfg, self.annoproj )
    self.annoIdx = self.annoDB.annoIdx
    self.index_dict = defaultdict(list)


  def createTables ( self  ):
    """Create the database tables""" 
    pass

  def buildIndex ( self,resolution):
    """Build the index for an annotation"""

    [ximagesz, yimagesz] = self.dbcfg.imagesz [ 1 ]
    [xcubedim, ycubedim, zcubedim] = self.dbcfg.cubedim [ 1 ]

      # Get the slices
    [ startslice, endslice ] = self.dbcfg.slicerange
    slices = endslice - startslice + 1
    
      # Set the limits for iteration on the number of cubes in each dimension
    xlimit = ximagesz / xcubedim
    ylimit = yimagesz / ycubedim
    #  Round up the zlimit to the next larger
    zlimit = (((slices-1)/zcubedim+1)*zcubedim)/zcubedim 

      # Round up to the top of the range
    lastzindex = (zindex.XYZMorton([xlimit,ylimit,zlimit])/64+1)*64
    
      # Iterate over the cubes in morton order
    for mortonidx in range(0, lastzindex, 64): 
      
      print "Working on batch %s at %s" % (mortonidx, zindex.MortonXYZ(mortonidx))
      
        # call the range query
      self.annoDB.queryRange ( mortonidx, mortonidx+64, 1 );
      
      # Flag to indicate no data.  No update query
      somedata = False
      
      # get the first cube
      [key,cube]  = self.annoDB.getNextCube ()
      
      #  if there's a cube, there's data
      if key != None:
        somedata = True
        
        while key != None:
          xyz = zindex.MortonXYZ ( key )
#          print "Found data in cube",key
          
          it = np.nditer ( cube.data, flags=['multi_index'])
          while not it.finished:
            if (it[0] != 0):
              #There is an annotation found at this location
              annid = int(it[0])
              
              #store annid and cube number in the index
              self.updateIdx(annid,key)
            it.iternext()

          # Get the next value
          [key,cube]  = self.annoDB.getNextCube ()

    #print the index -TESTING
#    for key, value in self.index_dict.iteritems():
 #     print key, value
    self.storeIndex(resolution)

    pass

  def updateIdx ( self, annid,key  ):
    """Add key /value to in momory idx tables"""
    if ( self.index_dict.has_key(annid)):
      flag = 0;
               # import pdb;pdb.set_trace()                                     
      for k,v in self.index_dict.iteritems():
        if k == annid:
          for val in range(0,len(v)):
            if v[val] == key:
              flag =1
      if flag == 0:
        self.index_dict[annid].append(int(key))
        
    else:
      print"Adding ", annid, " to the dictionary with value ", key
      self.index_dict[annid]=[]
      self.index_dict[annid].append(int(key))
      
    pass

  def storeIndex(self,resolution):
    print "In Store Index"
    for key, value in self.index_dict.iteritems():
#      print key, value
      self.annoIdx.saveIndex(key,value,resolution)
    pass

def main():

  parser = argparse.ArgumentParser(description='Build an index for the annotations')
  parser.add_argument('token', action="store", help='Token for the annotation project.')
  parser.add_argument('resolution', action="store", help='resolution for the annotation project.')
    
  result = parser.parse_args()

  # Create the annotation stack
  annstack = CreateIndex ( result.token )

  # Iterate over the database creating the hierarchy
  annstack.buildIndex ( result.resolution )
 # annstack.buildIndex ( )
  



if __name__ == "__main__":
  main()

