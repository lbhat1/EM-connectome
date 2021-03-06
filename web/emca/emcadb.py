import numpy as np
import cStringIO
import zlib
import MySQLdb
from collections import defaultdict

import zindex
import anncube
import imagecube
import emcaproj
import annotation
import annindex
import imagecube
import chancube

from emcaerror import ANNError

from emca_cy import cubeLocs_cy

import logging
logger=logging.getLogger("emca")

import sys

################################################################################
#
#  class: EMCADB
#
#  Manipulate/create/read from the Morton-order cube store
#
################################################################################


class EMCADB: 

  def __init__ (self, dbconf, annoproj):
    """Connect with the brain databases"""

    self.dbcfg = dbconf
    self.annoproj = annoproj

    # Are there exceptions?
    self.EXCEPT_FLAG = self.annoproj.getExceptions()

    # Connection info 
    try:
      self.conn = MySQLdb.connect (host = self.annoproj.getDBHost(),
                            user = self.annoproj.getDBUser(),
                            passwd = self.annoproj.getDBPasswd(),
                            db = self.annoproj.getDBName())
    except MySQLdb.Error, e:
      self.conn = None
      logger.error("Failed to connect to database: %s, %s" % (self.annoproj.getDBHost(), self.annoproj.getDBName()))
      raise

    self.cursor = self.conn.cursor()
      
    # How many slices?
    [ self.startslice, endslice ] = self.dbcfg.slicerange
    self.slices = endslice - self.startslice + 1 

    # create annidx object
    self.annoIdx = annindex.AnnotateIndex (self.conn, self.cursor, self.annoproj)

  def commit ( self ):
    """Commit the transaction.  Moved out of __del__ to make explicit.""" 
    self.conn.commit()

  def startTxn ( self ):
    """Start a transaction.  Ensure database is in multi-statement mode."""
    sql = "START TRANSACTION"
    self.cursor.execute ( sql )

  def rollback ( self ):
    """Rollback the transaction.  To be called on exceptions."""
    self.conn.rollback()

  def __del__ ( self ):
    """Close the connection"""
    if self.conn:
      self.cursor.close()
      self.conn.close()

  #
  #  peekID
  #
  def peekID ( self ):
    """Look at the next ID but don't claim it.  This is an internal interface.
        It is not thread safe.  Need a way to lock the ids table for the 
        transaction to make it safe."""
    
    # Query the current max identifier
    sql = "SELECT max(id) FROM " + str ( self.annoproj.getIDsTbl() )
    try:
      self.cursor.execute ( sql )
    except MySQLdb.Error, e:
      logger.warning ("Problem retrieving identifier %d: %s. sql=%s" % (e.args[0], e.args[1], sql))
      raise

    # Here we've queried the highest id successfully    
    row = self.cursor.fetchone()
    # if the table is empty start at 1, 0 is no annotation
    if ( row[0] == None ):
      identifier = 1
    else:
      identifier = int ( row[0] ) + 1

    return identifier

  #
  #  nextIdentifier
  #
  def nextID ( self ):
    """Get an new identifier.
       This is it's own txn and should not be called inside another transaction. """
    
    # LOCK the table to prevent race conditions on the ID
    sql = "LOCK TABLES %s WRITE" % ( self.annoproj.getIDsTbl() )
    try:

      self.cursor.execute ( sql )

      # Query the current max identifier
      sql = "SELECT max(id) FROM " + str ( self.annoproj.getIDsTbl() ) 
      try:
        self.cursor.execute ( sql )
      except MySQLdb.Error, e:
        logger.error ( "Failed to create annotation identifier %d: %s. sql=%s" % (e.args[0], e.args[1], sql))
        raise

      # Here we've queried the highest id successfully    
      row = self.cursor.fetchone ()
      # if the table is empty start at 1, 0 is no annotation
      if ( row[0] == None ):
        identifier = 1
      else:
        identifier = int ( row[0] ) + 1

      # increment and update query
      sql = "INSERT INTO " + str(self.annoproj.getIDsTbl()) + " VALUES ( " + str(identifier) + " ) "
      try:
        self.cursor.execute ( sql )
      except MySQLdb.Error, e:
        logger.error ( "Failed to insert into identifier table: %d: %s. sql=%s" % (e.args[0], e.args[1], sql))
        raise

    finally:
      pass
      sql = "UNLOCK TABLES" 
      self.cursor.execute ( sql )

    self.commit()
    return identifier


  #
  #  setID
  # 
  #  Place the user selected id into the ids table
  #
  def setID ( self, annoid ):
    """Set a user specified identifier"""

    # try the insert, get ane exception if it doesn't work
    sql = "INSERT INTO " + str(self.annoproj.getIDsTbl()) + " VALUES ( " + str(annoid) + " ) "
    try:
      self.cursor.execute ( sql )
    except MySQLdb.Error, e:
      logger.warning ( "Failed to set identifier table: %d: %s. sql=%s" % (e.args[0], e.args[1], sql))
      raise

    self.commit()
    return annoid


  #
  # getCube
  #
  def getCube ( self, key, resolution, update=False ):
    """Load a cube from the annotation database"""

    # get the size of the image and cube
    [ xcubedim, ycubedim, zcubedim ] = cubedim = self.dbcfg.cubedim [ resolution ] 

    # Create a cube object
    cube = anncube.AnnotateCube ( cubedim )

    # get the block from the database
    sql = "SELECT cube FROM " + self.annoproj.getTable(resolution) + " WHERE zindex = " + str(key) 
    if update==True:
          sql += " FOR UPDATE"

    try:
      self.cursor.execute ( sql )
    except MySQLdb.Error, e:
      logger.error ( "Failed to retrieve data cube: %d: %s. sql=%s" % (e.args[0], e.args[1], sql))
      raise

    row = self.cursor.fetchone()

    # If we can't find a cube, assume it hasn't been written yet
    if ( row == None ):
      cube.zeros ()
    else: 
      # decompress the cube
      cube.fromNPZ ( row[0] )

    return cube


  #
  # putCube
  #
  def putCube ( self, key, resolution, cube ):
    """Store a cube from the annotation database"""

    # compress the cube
    npz = cube.toNPZ ()

    # we created a cube from zeros
    if cube.fromZeros ():

      sql = "INSERT INTO " + self.annoproj.getTable(resolution) +  "(zindex, cube) VALUES (%s, %s)"

      # this uses a cursor defined in the caller (locking context): not beautiful, but needed for locking
      try:
        self.cursor.execute ( sql, (key,npz))
      except MySQLdb.Error, e:
        logger.error ( "Error inserting cube: %d: %s. sql=%s" % (e.args[0], e.args[1], sql))
        raise

    else:

      sql = "UPDATE " + self.annoproj.getTable(resolution) + " SET cube=(%s) WHERE zindex=" + str(key)
      try:
        self.cursor.execute ( sql, (npz))
      except MySQLdb.Error, e:
        logger.error ( "Error updating data cube: %d: %s. sql=%s" % (e.args[0], e.args[1], sql))
        raise


  #
  # queryRange
  #
  def queryRange ( self, lowkey, highkey, resolution ):
    """Create a stateful query to a range of values not including the high value.
         To be used with getNextCube().
         Not thread safe (context per object)
         Also, one cursor only.  Not at multiple resolutions"""

    self._qr_cursor = self.conn.cursor ()
    self._qr_resolution = resolution

    # get the block from the database
    sql = "SELECT zindex, cube FROM " + self.annoproj.getTable(resolution) + " WHERE zindex >= " + str(lowkey) + " AND zindex < " + str(highkey)

    try:
      self._qr_cursor.execute ( sql )
    except MySQLdb.Error, e:
      logger.error ( "Failed to retrieve data cube : %d: %s. sql=%s" % (e.args[0], e.args[1], sql))
      raise

  
  #
  # getNextCube
  #
  def getNextCube ( self ):
    """Retrieve the next cube in a queryRange.
         Not thread safe (context per object)"""

    # get the size of the image and cube
    [ xcubedim, ycubedim, zcubedim ] = cubedim = self.dbcfg.cubedim [ self._qr_resolution ] 

    # Create a cube object
    cube = anncube.AnnotateCube ( cubedim )

    row = self._qr_cursor.fetchone()

    # If we can't find a cube, assume it hasn't been written yet
    if ( row == None ):
      cube.zeros ()
      self._qr_cursor.close()
      return [None,None]
    else: 
      # decompress the cube
      cube.fromNPZ ( row[1] )
      return [row[0],cube]

  #
  # getExceptions
  #
  def getExceptions ( self, key, resolution, entityid ):
    """Load a the list of excpetions for this cube"""

    # get the block from the database
    sql = "SELECT exlist FROM %s where zindex=%s AND id=%s" % ( 'exc'+str(resolution), key, entityid )
    try:
      self.cursor.execute ( sql )
    except MySQLdb.Error, e:
      logger.error ( "Error reading exceptions %d: %s. sql=%s" % (e.args[0], e.args[1], sql))
      raise

    row = self.cursor.fetchone()

    # If we can't find a list of exceptions, they don't exist
    if ( row == None ):
      return []
    else: 
      fobj = cStringIO.StringIO ( zlib.decompress(row[0]) )
      return np.load (fobj)

  #
  # getAllExceptions
  #
  def getAllExceptions ( self, key, resolution ):
    """Load all exceptions for this cube"""

    # get the block from the database
    sql = "SELECT id, exlist FROM %s where zindex=%s" % ( 'exc'+str(resolution), key )
    try:
      self.cursor.execute ( sql )
    except MySQLdb.Error, e:
      logger.error ( "Error reading exceptions %d: %s. sql=%s" % (e.args[0], e.args[1], sql))
      raise

    row = cursor.fetchall()

    # If we can't find a list of exceptions, they don't exist
    if ( row == None ):
      return []
    else: 
      fobj = cStringIO.StringIO ( zlib.decompress(row[0]) )
      return np.load (fobj)

  #
  # updateExceptions
  #
  def updateExceptions ( self, key, resolution, entityid, exceptions ):
    """Store a list of exceptions"""

    curexlist = self.getExceptions( key, resolution, entityid ) 

    table = 'exc'+str(resolution)

    if curexlist==[]:

      sql = "INSERT INTO " + table + " (zindex, id, exlist) VALUES (%s, %s, %s)"
      try:
        fileobj = cStringIO.StringIO ()
        np.save ( fileobj, exceptions )
        self.cursor.execute ( sql, (key, entityid, zlib.compress(fileobj.getvalue())))
      except MySQLdb.Error, e:
        logger.error ( "Error inserting exceptions %d: %s. sql=%s" % (e.args[0], e.args[1], sql))
        raise

    # In this case we have an update query
    else:

      oldexlist = [ zindex.XYZMorton ( trpl ) for trpl in curexlist ]
      newexlist = [ zindex.XYZMorton ( trpl ) for trpl in exceptions ]
      exlist = set(newexlist + oldexlist)
      exlist = [ zindex.MortonXYZ ( zidx ) for zidx in exlist ]

      sql = "UPDATE " + table + " SET exlist=(%s) WHERE zindex=%s AND id=%s" 
      try:
        fileobj = cStringIO.StringIO ()
        np.save ( fileobj, exlist )
        self.cursor.execute ( sql, (zlib.compress(fileobj.getvalue()),key,entityid))
      except MySQLdb.Error, e:
        logger.error ( "Error updating exceptions %d: %s. sql=%s" % (e.args[0], e.args[1], sql))
        raise

  #
  # removeExceptions
  #
  def removeExceptions ( self, key, resolution, entityid, exceptions ):
    """Remove a list of exceptions"""

    curexlist = self.getExceptions( key, resolution, entityid ) 

    table = 'exc'+str(resolution)

    if curexlist != []:

      oldexlist = set([ zindex.XYZMorton ( trpl ) for trpl in curexlist ])
      newexlist = set([ zindex.XYZMorton ( trpl ) for trpl in exceptions ])
      exlist = oldexlist-newexlist
      exlist = [ zindex.MortonXYZ ( zidx ) for zidx in exlist ]

      sql = "UPDATE " + table + " SET exlist=(%s) WHERE zindex=%s AND id=%s" 
      try:
        fileobj = cStringIO.StringIO ()
        np.save ( fileobj, exlist )
        self.cursor.execute ( sql, (zlib.compress(fileobj.getvalue()),key,entityid))
      except MySQLdb.Error, e:
        logger.error("Error removing exceptions %d: %s. sql=%s" % (e.args[0], e.args[1], sql))
        raise

  #
  # annotate
  #
  #  number the voxels and build the exceptions
  #
  def annotate ( self, entityid, resolution, locations, conflictopt='O' ):
    """Label the voxel locations or add as exceptions is the are already labeled."""

    [ xcubedim, ycubedim, zcubedim ] = cubedim = self.dbcfg.cubedim [ resolution ] 

    #  An item may exist across several cubes
    #  Convert the locations into Morton order

    # dictionary with the index
    cubeidx = defaultdict(set)

    # convert voxels z coordinate
    locations[:,2] = locations[:,2] - self.dbcfg.slicerange[0]

    cubelocs = cubeLocs_cy ( np.array(locations, dtype=np.uint32), cubedim )

    # sort the arrary, by cubeloc
    cubelocs.view('u4,u4,u4,u4').sort(order=['f0'], axis=0)

    # get the nonzero element offsets 
    nzdiff = np.r_[np.nonzero(np.diff(cubelocs[:,0]))]
    # then turn into a set of ranges of the same element
    listoffsets = np.r_[0, nzdiff + 1, len(cubelocs)]

    for i in range(len(listoffsets)-1):

      # grab the list of voxels for the first cube
      voxlist = cubelocs[listoffsets[i]:listoffsets[i+1],:][:,1:4]
      #  and the morton key
      key = cubelocs[listoffsets[i],0]

      cube = self.getCube ( key, resolution, True )

      # get a voxel offset for the cube
      cubeoff = zindex.MortonXYZ(key)
      offset = [cubeoff[0]*cubedim[0],cubeoff[1]*cubedim[1],cubeoff[2]*cubedim[2]]

      # add the items
      exceptions = np.array(cube.annotate(entityid, offset, voxlist, conflictopt), dtype=np.uint8)

      # update the sparse list of exceptions
      if self.EXCEPT_FLAG:
        if len(exceptions) != 0:
          self.updateExceptions ( key, resolution, entityid, exceptions )

      self.putCube ( key, resolution, cube)

      # add this cube to the index
      cubeidx[entityid].add(key)

    # write it to the database
    self.annoIdx.updateIndexDense(cubeidx,resolution)

  #
  # shave
  #
  #  reduce the voxels 
  #
  def shave ( self, entityid, resolution, locations ):
    """Label the voxel locations or add as exceptions is the are already labeled."""

    [ xcubedim, ycubedim, zcubedim ] = cubedim = self.dbcfg.cubedim [ resolution ] 

    # dictionary with the index
    cubeidx = defaultdict(set)

    # convert voxels z coordinate
    locations[:,2] = locations[:,2] - self.dbcfg.slicerange[0]

    cubelocs = cubeLocs_cy ( np.array(locations, dtype=np.uint32), cubedim )

    # sort the arrary, by cubeloc
    cubelocs.view('u4,u4,u4,u4').sort(order=['f0'], axis=0)

    # get the nonzero element offsets 
    nzdiff = np.r_[np.nonzero(np.diff(cubelocs[:,0]))]
    # then turn into a set of ranges of the same element
    listoffsets = np.r_[0, nzdiff + 1, len(cubelocs)]

    for i in range(len(listoffsets)-1):

      # grab the list of voxels for the first cube
      voxlist = cubelocs[listoffsets[i]:listoffsets[i+1],:][:,1:4]
      #  and the morton key
      key = cubelocs[listoffsets[i],0]

      cube = self.getCube ( key, resolution, True )

      # get a voxel offset for the cube
      cubeoff = zindex.MortonXYZ(key)
      offset = [cubeoff[0]*cubedim[0],cubeoff[1]*cubedim[1],cubeoff[2]*cubedim[2]]

      # remove the items
      exlist, zeroed = cube.shave(entityid, offset, voxlist)
      # make sure that exceptions are stored as 8 bits
      exceptions = np.array(exlist, dtype=np.uint8)

      # update the sparse list of exceptions
      if self.EXCEPT_FLAG:
        if len(exceptions) != 0:
          self.removeExceptions ( key, resolution, entityid, exceptions )

      # zeroed is the list that needs to get promoted here.
      # RBTODO

      self.putCube ( key, resolution, cube)

      # For now do no index processing when shaving.  Assume there are still some
      #  voxels in the cube???


  #
  # annotateDense
  #
  #  Process a cube of data that has been labelled with annotations.
  #
  def annotateDense ( self, corner, resolution, annodata, conflictopt ):
    """Process all the annotations in the dense volume"""

    index_dict = defaultdict(set)

    # dim is in xyz, data is in zyxj
    dim = [ annodata.shape[2], annodata.shape[1], annodata.shape[0] ]

    # get the size of the image and cube
    [ xcubedim, ycubedim, zcubedim ] = cubedim = self.dbcfg.cubedim [ resolution ] 

    # Round to the nearest larger cube in all dimensions
    zstart = corner[2]/zcubedim
    ystart = corner[1]/ycubedim
    xstart = corner[0]/xcubedim

    znumcubes = (corner[2]+dim[2]+zcubedim-1)/zcubedim - zstart
    ynumcubes = (corner[1]+dim[1]+ycubedim-1)/ycubedim - ystart
    xnumcubes = (corner[0]+dim[0]+xcubedim-1)/xcubedim - xstart

    zoffset = corner[2]%zcubedim
    yoffset = corner[1]%ycubedim
    xoffset = corner[0]%xcubedim

    databuffer = np.zeros ([znumcubes*zcubedim, ynumcubes*ycubedim, xnumcubes*xcubedim], dtype=np.uint32 )
    databuffer [ zoffset:zoffset+dim[2], yoffset:yoffset+dim[1], xoffset:xoffset+dim[0] ] = annodata 

    for z in range(znumcubes):
      for y in range(ynumcubes):
        for x in range(xnumcubes):

          key = zindex.XYZMorton ([x+xstart,y+ystart,z+zstart])
          cube = self.getCube ( key, resolution, True )

          if conflictopt == 'O':
            cube.overwrite ( databuffer [ z*zcubedim:(z+1)*zcubedim, y*ycubedim:(y+1)*ycubedim, x*xcubedim:(x+1)*xcubedim ] )
          elif conflictopt == 'P':
            cube.preserve ( databuffer [ z*zcubedim:(z+1)*zcubedim, y*ycubedim:(y+1)*ycubedim, x*xcubedim:(x+1)*xcubedim ] )
          elif conflictopt == 'E' and self.EXCEPT_FLAG:
            exdata = cube.exception ( databuffer [ z*zcubedim:(z+1)*zcubedim, y*ycubedim:(y+1)*ycubedim, x*xcubedim:(x+1)*xcubedim ] )
            for exid in np.unique ( exdata ):
              if exid != 0:
                # get the offsets
                exoffsets = np.nonzero ( exdata==exid )
                # assemble into 3-tuples zyx->xyz
                exceptions = np.array ( zip(exoffsets[2], exoffsets[1], exoffsets[0]), dtype=np.uint32 )
                # update the exceptions
                self.updateExceptions ( key, resolution, exid, exceptions )
                # add to the index
                index_dict[exid].add(key)
          else:
            raise ANNError ( "Unsupported conflict option %s" % conflictopt )

          self.putCube ( key, resolution, cube)

          #update the index for the cube
          # get the unique elements that are being added to the data
          uniqueels = np.unique ( databuffer [ z*zcubedim:(z+1)*zcubedim, y*ycubedim:(y+1)*ycubedim, x*xcubedim:(x+1)*xcubedim ] )
          for el in uniqueels:
            index_dict[el].add(key) 

          # remove 0 no reason to index that
          del(index_dict[0])


    # Update all indexes
    self.annoIdx.updateIndexDense(index_dict,resolution)

  #
  #  Called when labeling an entity
  #
  def annotateEntityDense ( self, entityid, corner, resolution, annodata, conflictopt ):
    """Relabel all nonzero pixels to annotation id and call annotateDense"""

    vec_func = np.vectorize ( lambda x: 0 if x == 0 else entityid ) 
    annodata = vec_func ( annodata )
    return self.annotateDense ( corner, resolution, annodata, conflictopt )

  #
  # shaveDense
  #
  #  Reduce the specified annotations 
  #
  def shaveDense ( self, entityid, corner, resolution, annodata ):
    """Process all the annotations in the dense volume"""


    index_dict = defaultdict(set)

    # dim is in xyz, data is in zyxj
    dim = [ annodata.shape[2], annodata.shape[1], annodata.shape[0] ]

    # get the size of the image and cube
    [ xcubedim, ycubedim, zcubedim ] = cubedim = self.dbcfg.cubedim [ resolution ] 

    # Round to the nearest larger cube in all dimensions
    zstart = corner[2]/zcubedim
    ystart = corner[1]/ycubedim
    xstart = corner[0]/xcubedim

    znumcubes = (corner[2]+dim[2]+zcubedim-1)/zcubedim - zstart
    ynumcubes = (corner[1]+dim[1]+ycubedim-1)/ycubedim - ystart
    xnumcubes = (corner[0]+dim[0]+xcubedim-1)/xcubedim - xstart

    zoffset = corner[2]%zcubedim
    yoffset = corner[1]%ycubedim
    xoffset = corner[0]%xcubedim

    databuffer = np.zeros ([znumcubes*zcubedim, ynumcubes*ycubedim, xnumcubes*xcubedim], dtype=np.uint32 )
    databuffer [ zoffset:zoffset+dim[2], yoffset:yoffset+dim[1], xoffset:xoffset+dim[0] ] = annodata 

    for z in range(znumcubes):
      for y in range(ynumcubes):
        for x in range(xnumcubes):

          key = zindex.XYZMorton ([x+xstart,y+ystart,z+zstart])
          cube = self.getCube ( key, resolution, True )

          exdata = cube.shaveDense ( databuffer [ z*zcubedim:(z+1)*zcubedim, y*ycubedim:(y+1)*ycubedim, x*xcubedim:(x+1)*xcubedim ] )
          for exid in np.unique ( exdata ):
            if exid != 0:
              # get the offsets
              exoffsets = np.nonzero ( exdata==exid )
              # assemble into 3-tuples zyx->xyz
              exceptions = np.array ( zip(exoffsets[2], exoffsets[1], exoffsets[0]), dtype=np.uint32 )
              # update the exceptions
              self.removeExceptions ( key, resolution, exid, exceptions )
              # add to the index
              index_dict[exid].add(key)

          self.putCube ( key, resolution, cube)

          #update the index for the cube
          # get the unique elements that are being added to the data
          uniqueels = np.unique ( databuffer [ z*zcubedim:(z+1)*zcubedim, y*ycubedim:(y+1)*ycubedim, x*xcubedim:(x+1)*xcubedim ] )
          for el in uniqueels:
            index_dict[el].add(key) 

          # remove 0 no reason to index that
          del(index_dict[0])

    # Update all indexes
    self.annoIdx.updateIndexDense(index_dict,resolution)

  #
  # shaveEntityDense
  #
  #  Takes a bitmap for an entity and calls denseShave
  #  renumber the annotations to match the entity id.
  #
  def shaveEntityDense ( self, entityid, corner, resolution, annodata ):
    """Process all the annotations in the dense volume"""

    # Make shaving a per entity operation
    vec_func = np.vectorize ( lambda x: 0 if x == 0 else entityid ) 
    annodata = vec_func ( annodata )

    self.shaveDense ( entityid, corner, resolution, annodata )


  #
  #  Return a cube of data from the database
  #  Must account for zeros.
  #
  def cutout ( self, corner, dim, resolution, channel=None ):
    """Extract a cube of arbitrary size.  Need not be aligned."""
    
    # get the size of the image and cube
    [ xcubedim, ycubedim, zcubedim ] = cubedim = self.dbcfg.cubedim [ resolution ] 

    # Round to the nearest larger cube in all dimensions
    zstart = corner[2]/zcubedim
    ystart = corner[1]/ycubedim
    xstart = corner[0]/xcubedim

    znumcubes = (corner[2]+dim[2]+zcubedim-1)/zcubedim - zstart
    ynumcubes = (corner[1]+dim[1]+ycubedim-1)/ycubedim - ystart
    xnumcubes = (corner[0]+dim[0]+xcubedim-1)/xcubedim - xstart

    if (self.annoproj.getDBType() == emcaproj.ANNOTATIONS):

      # input cube is the database size
      incube = anncube.AnnotateCube ( cubedim )

      # output cube is as big as was asked for and zero it.
      outcube = anncube.AnnotateCube ( [xnumcubes*xcubedim,\
                                        ynumcubes*ycubedim,\
                                        znumcubes*zcubedim] )
      outcube.zeros()

    elif (self.annoproj.getDBType() == emcaproj.IMAGES):
      
      incube = imagecube.ImageCube ( cubedim )
      outcube = imagecube.ImageCube ( [xnumcubes*xcubedim,\
                                        ynumcubes*ycubedim,\
                                        znumcubes*zcubedim] )

    elif (self.annoproj.getDBType() == emcaproj.CHANNELS):
      
      incube = chancube.ChanCube ( cubedim )
      outcube = chancube.ChanCube ( [xnumcubes*xcubedim,\
                                        ynumcubes*ycubedim,\
                                        znumcubes*zcubedim] )

    # Build a list of indexes to access
    listofidxs = []
    for z in range ( znumcubes ):
      for y in range ( ynumcubes ):
        for x in range ( xnumcubes ):
          mortonidx = zindex.XYZMorton ( [x+xstart, y+ystart, z+zstart] )
          listofidxs.append ( mortonidx )

    # Sort the indexes in Morton order
    listofidxs.sort()

    # Batch query for all cubes
    dbname = self.annoproj.getTable(resolution)

    # Customize query to the database (include channel or not)
    if (self.annoproj.getDBType() == emcaproj.CHANNELS):
      sql = "SELECT zindex, cube FROM " + dbname + " WHERE channel= " + str(channel) + " AND zindex in (%s)" 
    else:
      sql = "SELECT zindex, cube FROM " + dbname + " WHERE zindex IN (%s)" 

    # creats a %s for each list element
    in_p=', '.join(map(lambda x: '%s', listofidxs))
    # replace the single %s with the in_p string
    sql = sql % in_p
    rc = self.cursor.execute(sql, listofidxs)

    # xyz offset stored for later use
    lowxyz = zindex.MortonXYZ ( listofidxs[0] )

    # Get the objects and add to the cube
    while ( True ):
      try: 
        idx, datastring = self.cursor.fetchone()
      except:
        break

      #add the query result cube to the bigger cube
      curxyz = zindex.MortonXYZ(int(idx))
      offset = [ curxyz[0]-lowxyz[0], curxyz[1]-lowxyz[1], curxyz[2]-lowxyz[2] ]

      incube.fromNPZ ( datastring[:] )
      # add it to the output cube
      outcube.addData ( incube, offset ) 
        
    # need to trim down the array to size
    #  only if the dimensions are not the same
    if dim[0] % xcubedim  == 0 and\
       dim[1] % ycubedim  == 0 and\
       dim[2] % zcubedim  == 0 and\
       corner[0] % xcubedim  == 0 and\
       corner[1] % ycubedim  == 0 and\
       corner[2] % zcubedim  == 0:
      pass
    else:
      outcube.trim ( corner[0]%xcubedim,dim[0],\
                      corner[1]%ycubedim,dim[1],\
                      corner[2]%zcubedim,dim[2] )

    return outcube


  #
  # getVoxel -- return the identifier at a voxel
  #
  #
  def getVoxel ( self, resolution, voxel ):
    """Return the identifier at a voxel"""

    # get the size of the image and cube
    [ xcubedim, ycubedim, zcubedim ] = cubedim = self.dbcfg.cubedim [ resolution ] 

    # convert the voxel into zindex and offsets
    # Round to the nearest larger cube in all dimensions
    xyzcube = [ voxel[0]/xcubedim, voxel[1]/ycubedim, (voxel[2]-self.startslice)/zcubedim ]
    xyzoffset =[ voxel[0]%xcubedim, voxel[1]%ycubedim, (voxel[2]-self.startslice)%zcubedim ]

    # Create a cube object
    cube = anncube.AnnotateCube ( cubedim )

    mortonidx = zindex.XYZMorton ( xyzcube )

    # get the block from the database
    sql = "SELECT cube FROM " + self.annoproj.getTable(resolution) + " WHERE zindex = " + str(mortonidx)
    try:
      self.cursor.execute ( sql )
    except MySQLdb.Error, e:
      logger.warning ( "Error reading annotation data: %d: %s. sql=%s" % (e.args[0], e.args[1], sql))
      raise

    row=self.cursor.fetchone()

    # If we can't find a cube, assume it hasn't been written yet
    if ( row == None ):
      retval = 0
    else: 
      cube.fromNPZ ( row[0] )
      retval = cube.getVoxel ( xyzoffset )

    return retval


  # Alternate to getVolume that returns a annocube
  def annoCutout ( self, entityid, resolution, corner, dim ):
    """Fetch a volume cutout with only the specified annotation"""

    cube = self.cutout(corner,dim,resolution)
    vec_func = np.vectorize ( lambda x: np.uint32(0) if x != entityid else np.uint32(entityid)) 
    cube.data = vec_func ( cube.data )

    # And get the exceptions
    # get the size of the image and cube
    [ xcubedim, ycubedim, zcubedim ] = cubedim = self.dbcfg.cubedim [ resolution ] 

    # Round to the nearest larger cube in all dimensions
    zstart = corner[2]/zcubedim
    ystart = corner[1]/ycubedim
    xstart = corner[0]/xcubedim

    znumcubes = (corner[2]+dim[2]+zcubedim-1)/zcubedim - zstart
    ynumcubes = (corner[1]+dim[1]+ycubedim-1)/ycubedim - ystart
    xnumcubes = (corner[0]+dim[0]+xcubedim-1)/xcubedim - xstart

    zoffset = corner[2]%zcubedim
    yoffset = corner[1]%ycubedim
    xoffset = corner[0]%xcubedim

    for z in range(znumcubes):
      for y in range(ynumcubes):
        for x in range(xnumcubes):

          key = zindex.XYZMorton ([x+xstart,y+ystart,z+zstart])
          
          # Get exceptions if this DB supports it
          if self.EXCEPT_FLAG:
            exceptions = self.getExceptions( key, resolution, entityid ) 
            if exceptions != []:
              # write as a loop first, then figure out how to optimize 
              for e in exceptions:
                xloc = e[0]+(x+xstart)*xcubedim
                yloc = e[1]+(y+ystart)*ycubedim
                zloc = e[2]+(z+zstart)*zcubedim
                if xloc>=corner[0] and xloc<corner[0]+dim[0] and yloc>=corner[1] and yloc<corner[1]+dim[1] and zloc>=corner[2] and zloc<corner[2]+dim[2]:
                  cube.data[e[2]-zoffset+z*zcubedim,e[1]-yoffset+y*ycubedim,e[0]-xoffset+x*xcubedim]=entityid

    return cube

  #
  # getLocations -- return the list of locations associated with an identifier
  #
  def getLocations ( self, entityid, res ):

    # get the size of the image and cube
    resolution = int(res)

    voxlist = []

    zidxs = self.annoIdx.getIndex(entityid,resolution)

    for zidx in zidxs:

      cb = self.getCube (zidx,resolution) 

      # mask out the entries that do not match the annotation id
      vec_func = np.vectorize ( lambda x: entityid if x == entityid else 0 )
      annodata = vec_func ( cb.data )
    
      # where are the entries
      offsets = np.nonzero ( annodata ) 
      voxels = np.array(zip(offsets[2], offsets[1], offsets[0]), dtype=np.uint32)

      # Get cube offset information
      [x,y,z]=zindex.MortonXYZ(zidx)
      xoffset = x * self.dbcfg.cubedim[resolution][0] 
      yoffset = y * self.dbcfg.cubedim[resolution][1] 
      zoffset = z * self.dbcfg.cubedim[resolution][2] + self.dbcfg.slicerange[0]

      # Now add the exception voxels
      if self.EXCEPT_FLAG:
        exceptions = self.getExceptions( zidx, resolution, entityid ) 
        if exceptions != []:
          voxels = np.append ( voxels.flatten(), exceptions.flatten())
          voxels = voxels.reshape(len(voxels)/3,3)

      # Change the voxels back to image address space
      [ voxlist.append([a+xoffset, b+yoffset, c+zoffset]) for (a,b,c) in voxels ] 

    return voxlist

  #
  # getBoundingBox -- return a corner and dimension of the bounding box 
  #   for an annotation using the index.
  #
  def getBoundingBox ( self, entityid, res ):
  
    # get the size of the image and cube
    resolution = int(res)

    # all boxes in the index
    zidxs = self.annoIdx.getIndex(entityid,resolution)

    if len(zidxs)==0:
      return None, None
    
    # convert to xyz coordinates
    xyzvals = np.array ( [ zindex.MortonXYZ(zidx) for zidx in zidxs ], dtype=np.uint32 )

    cubedim = self.dbcfg.cubedim [ resolution ] 

    # find the corners
    xmin = min(xyzvals[:,0]) * cubedim[0]
    xmax = (max(xyzvals[:,0])+1) * cubedim[0]
    ymin = min(xyzvals[:,1]) * cubedim[1]
    ymax = (max(xyzvals[:,1])+1) * cubedim[1]
    zmin = min(xyzvals[:,2]) * cubedim[2]
    zmax = (max(xyzvals[:,2])+1) * cubedim[2]

    corner = [ xmin, ymin, zmin ]
    dim = [ xmax-xmin, ymax-ymin, zmax-zmin ]

    return (corner,dim)

  #
  # getAnnotation:  
  #    Look up an annotation, switch on what kind it is, build an HDF5 file and
  #     return it.
  def getAnnotation ( self, id ):
    """Return a RAMON object by identifier"""
    
    return annotation.getAnnotation( id, self )

  #
  # putAnnotation:  
  #    store an HDF5 annotation to the database
  def putAnnotation ( self, anno, options='' ):
    """store an HDF5 annotation to the database"""
    
    return annotation.putAnnotation( anno, self, options )

  #
  # deleteAnnotation:  
  #    remove an HDF5 annotation from the database
  def deleteAnnotation ( self, annoid, options='' ):
    """delete an HDF5 annotation from the database"""
    #delete the data associated with the annoid
    self.deleteAnnoData ( annoid)
    return annotation.deleteAnnotation ( annoid, self, options )
  
  #
  #deleteAnnoData:
  #    Delete the voxel data from the database for annoid 
  #
  def deleteAnnoData ( self, annoid):

    resolutions = self.dbcfg.resolutions

    for res in resolutions:
    
    #get the cubes that contain the annotation
      zidxs = self.annoIdx.getIndex(annoid,res,True)
      
    #Delete annotation data
      for key in zidxs:
        cube = self.getCube ( key, res, True )
        vec_func = np.vectorize ( lambda x: 0 if x == annoid else x )
        cube.data = vec_func ( cube.data )
        self.putCube ( key, res, cube)
      
    # delete Index
    self.annoIdx.deleteIndex(annoid,resolutions)

  
  # getAnnoObjects:  
  #    Return a list of annotation object IDs
  #  for now by type and status
  def getAnnoObjects ( self, predicates ):
    """Return a list of annotation object ids that match equality predicates.  
      Legal predicates are currently:
        type
        status
      Predicates are given in a dictionary.
    """

    # legal fields
    fields = ( 'type', 'status' )

    # start of the SQL clause
    sql = "SELECT annoid FROM " + annotation.anno_dbtables['annotation'] 

    clause = ''

    # probably need to avoid SQL injection attacks.
    #  throw an error or build the sql clause
    for field in predicates.keys():
      if field not in fields:
        raise ANNError ( "Illegal field in URL: %s" % (field) )
      elif clause == '':
        clause += " WHERE "
      else:  
        clause += ' AND '
      clause += '%s = %s' % ( field, predicates[field] )

    sql += clause + ';'

    try:
      self.cursor.execute ( sql )
    except MySQLdb.Error, e:
      logger.error ( "Error retrieving ids: %d: %s. sql=%s" % (e.args[0], e.args[1], sql))
      raise

    annoids = np.array ( self.cursor.fetchall(), dtype=np.uint32 ).flatten()

    return np.array(annoids)


  #
  # writeImageCuboid
  #
  #  Write an image through the Web service.  Make ingest easier.
  #
  def writeImageCuboid ( self, corner, resolution, imgdata ):
    """Write an image through the Web service"""

    # dim is in xyz, data is in zyxj
    dim = [ imgdata.shape[2], imgdata.shape[1], imgdata.shape[0] ]

    # get the size of the image and cube
    [ xcubedim, ycubedim, zcubedim ] = cubedim = self.dbcfg.cubedim [ resolution ] 

    # Round to the nearest larger cube in all dimensions
    zstart = corner[2]/zcubedim
    ystart = corner[1]/ycubedim
    xstart = corner[0]/xcubedim

    znumcubes = (corner[2]+dim[2]+zcubedim-1)/zcubedim - zstart
    ynumcubes = (corner[1]+dim[1]+ycubedim-1)/ycubedim - ystart
    xnumcubes = (corner[0]+dim[0]+xcubedim-1)/xcubedim - xstart

    zoffset = corner[2]%zcubedim
    yoffset = corner[1]%ycubedim
    xoffset = corner[0]%xcubedim

    databuffer = np.zeros ([znumcubes*zcubedim, ynumcubes*ycubedim, xnumcubes*xcubedim], dtype=np.uint8 )
    databuffer [ zoffset:zoffset+dim[2], yoffset:yoffset+dim[1], xoffset:xoffset+dim[0] ] = imgdata 

    for z in range(znumcubes):
      for y in range(ynumcubes):
        for x in range(xnumcubes):

          key = zindex.XYZMorton ([x+xstart,y+ystart,z+zstart])
          cube = self.getCube ( key, resolution, True )

          cube.data = databuffer [ z*zcubedim:(z+1)*zcubedim, y*ycubedim:(y+1)*ycubedim, x*xcubedim:(x+1)*xcubedim ] 

          self.putCube ( key, resolution, cube)

