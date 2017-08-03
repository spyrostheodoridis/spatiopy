from osgeo import osr,ogr,gdal
import pandas
import numpy

def getValuesAtPoint(indir, rasterfileList, pos, Lon, Lat):
    #gt(2) and gt(4) coefficients are zero, and the gt(1) is pixel width, and gt(5) is pixel height.
    #The (gt(0),gt(3)) position is the top left corner of the top left pixel of the raster.
    for i, rs in enumerate(rasterfileList):
        
        presValues = []
        gdata = gdal.Open('{}/{}.tif'.format(indir,rs))
        gt = gdata.GetGeoTransform()

        x0, y0 , w , h = gt[0], gt[3], gt[1], gt[5]

        data = gdata.ReadAsArray().astype(numpy.float)
        #free memory
        gdata = None
        
        if i == 0:
            #iterate through the points
            for p in pos.iterrows():
                x = int((p[1]['x'] - x0)/w)
                Xc = x0 + x*w + w/2 #the cell center x
                y = int((p[1]['y'] - y0)/h)
                Yc = y0 + y*h + h/2 #the cell center y
                try:
                    if data[y,x] != -9999.0:
                        presVAL = [p[1]['x'],p[1]['y'], '{:.6f}'.format(Xc), '{:.6f}'.format(Yc), data[y,x]]
                        presValues.append(presVAL)
                except:
                    pass
            df = pandas.DataFrame(presValues, columns=['x', 'y', 'Xc', 'Yc', rs])
        else:
            #iterate through the points
            for p in pos.iterrows():
                x = int((p[1]['x'] - x0)/w)
                y = int((p[1]['y'] - y0)/h)
                try:
                    if data[y,x] != -9999.0:
                        presValues.append(data[y,x])
                except:
                    pass
            df[rs] = pandas.Series(presValues)

    return df


#### function to get all pixel center coordinates and corresponding values from rasters
def getRasterValues(indir, rasterfileList):
    
    for i, rs in enumerate(rasterfileList):
        
        if i == 0:
            vList = []
            gdata = gdal.Open('{}/{}.tif'.format(indir,rs))
            gt = gdata.GetGeoTransform()
            data = gdata.ReadAsArray().astype(numpy.float)
            #free memory
            del gdata

            x0, y0 , w , h = gt[0], gt[3], gt[1], gt[5]

            for r, row in enumerate(data):
                x = 0
                for c, column in enumerate(row):
                    x = x0 + c*w + w/2
                    y = y0 + r*h + h/2

                    vList.append(['{:.6f}'.format(x),'{:.6f}'.format(y),column])
            df = pandas.DataFrame(vList, columns=['Xc', 'Yc', rs])
            
        else:
            gdata = gdal.Open('{}/{}.tif'.format(indir,rs))
            gt = gdata.GetGeoTransform()
            data = gdata.ReadAsArray().astype(numpy.float)
            #free memory
            gdata = None
            vList = [c for r in data for c in r]
            df[rs] = pandas.Series(vList)
    
    del data       
    return(df)


# geo raster to numpy array    
def raster2array(rasterfn):
    raster = gdal.Open(rasterfn)
    band = raster.GetRasterBand(1)
    nodata = band.GetNoDataValue()
    array = band.ReadAsArray()
    
    proj = raster.GetProjection()
    inproj = osr.SpatialReference()
    inproj.ImportFromWkt(proj)
    
    geoTransform = raster.GetGeoTransform()
    minx = geoTransform[0]
    maxy = geoTransform[3]
    maxx = minx + geoTransform[1]*raster.RasterXSize
    miny = maxy + geoTransform[5]*raster.RasterYSize
    extent =  [minx, maxx, miny, maxy]
    pixelSizeXY = [geoTransform[1], geoTransform[5]]
    del raster, band
    return [array, nodata, extent, inproj, pixelSizeXY]

# create a reference raster with random values    
def createRaster(outRas, extCells, pixelSize, dataType = "float32"):
    NP2GDAL_CONVERSION = { "uint8": 1, "int8": 1, "uint16": 2, "int16": 3, 
                          "uint32": 4, "int32": 5, "float32": 6, "float64": 7,
                          "complex64": 10, "complex128": 11,
                         }
    
    # Create the destination data source        
    xRes = int(numpy.ceil((extCells[2] - extCells[0]) / pixelSize))
    yRes = int(numpy.ceil((extCells[3] - extCells[1]) / pixelSize))

    targetRas = gdal.GetDriverByName('GTiff').Create(outRas, xRes, yRes, 1, NP2GDAL_CONVERSION[dataType])
    targetRas.SetGeoTransform((extCells[0], pixelSize, 0, extCells[3], 0, -pixelSize))
    
    g = numpy.zeros((yRes,xRes), eval('numpy.{}'.format(dataType)))
    
    for i in range(yRes):
        for j in range(xRes):
            g[i,j] = numpy.random.random_sample()

    targetRasSRS = osr.SpatialReference()
    targetRasSRS.ImportFromEPSG(4326)
    targetRas.SetProjection(targetRasSRS.ExportToWkt())

    band = targetRas.GetRasterBand(1)
    band.SetNoDataValue(-9999)
    band.WriteArray(g)
    band.FlushCache()

#function to filter raster cells based on the coverage by some vector features
def filterByCoverage(vectorFile, rasterFile, covPerc):
    
    srcVector = ogr.Open(vectorFile)
    srcLayer = srcVector.GetLayer()
    # merge all features in one geometry (multi polygone)
    multi  = ogr.Geometry(ogr.wkbMultiPolygon)
    for feature in srcLayer:
        geom = feature.GetGeometryRef()
        multi.AddGeometry(geom)
    
    #attributes of raster file
    rasList = raster2array(rasterFile)

    xsize = rasList[4][0]
    ysize = abs(rasList[4][1])

    pixel_area = xsize*ysize

    rows = rasList[0].shape[0]
    cols = rasList[0].shape[1]

    x1 = rasList[2][0]
    y1 = rasList[2][3]
    
    #iterate over raster cells
    for i in range(rows):
        for j in range(cols):
            ring = ogr.Geometry(ogr.wkbLinearRing)

            ring.AddPoint(x1, y1)
            ring.AddPoint(x1 + xsize, y1)
            ring.AddPoint(x1 + xsize, y1 - ysize)
            ring.AddPoint(x1, y1 - ysize)
            ring.AddPoint(x1, y1)

            poly = ogr.Geometry(ogr.wkbPolygon)
            poly.AddGeometry(ring)

            intersect = multi.Intersection(poly)

            if intersect.ExportToWkt() != 'GEOMETRYCOLLECTION EMPTY':
                perc = (intersect.GetArea()/pixel_area)*100
                if perc > covPerc:
                    rasList[0][i][j] = numpy.nan     
            x1 += xsize
        x1 = rasList[2][0]
        y1 -= ysize
    
    return(rasList[0]) #return the filtered array


# numpy array to geo raster
def array2raster(newRaster, RefRaster, array, noData, dataType):
    #data type conversion
    NP2GDAL_CONVERSION = { "uint8": 1, "int8": 1, "uint16": 2, "int16": 3, 
                          "uint32": 4, "int32": 5, "float32": 6, "float64": 7,
                          "complex64": 10, "complex128": 11,
                         }
    #get info from reference raster
    rfRaster = gdal.Open(RefRaster)
    geotransform = rfRaster.GetGeoTransform()
    originX = geotransform[0]
    originY = geotransform[3]
    pixelWidth = geotransform[1]
    pixelHeight = geotransform[5]
    cols = array.shape[1]
    rows = array.shape[0]
    #create new raster
    outRaster = gdal.GetDriverByName('GTiff').Create(newRaster, cols, rows,1, NP2GDAL_CONVERSION[dataType])
    outRaster.SetGeoTransform((originX, pixelWidth, 0, originY, 0, pixelHeight))
    #write array to band
    outband = outRaster.GetRasterBand(1)
    outband.SetNoDataValue(noData)
    outband.WriteArray(array)
    #define new raster projection
    outRasterSRS = osr.SpatialReference()
    outRasterSRS.ImportFromWkt(rfRaster.GetProjectionRef())
    outRaster.SetProjection(outRasterSRS.ExportToWkt())
    #write raster
    outband.FlushCache()
    del rfRaster
    

    
 