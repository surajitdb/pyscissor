#!/usr/bin/env python3

'''
'''


import sys
import fiona
import argparse
import numpy as np
import pandas as pd
from tqdm import tqdm
from pyscissor import scissor
from shapely.geometry import shape
from datetime import datetime as dt
from netCDF4 import Dataset,num2date



def main():
    arg_parser=argparse.ArgumentParser()

    arg_parser.add_argument('-n', '--netcdf', dest="nc",required=True,
                            type=str,default=None, help="netcdf file location")

    arg_parser.add_argument('-ni', '--netcdf-info', dest="nci",required=True,
                            type=str,default=None, help="netcdf file details")

    arg_parser.add_argument('-s', '--shapefile', dest="shp",required=True,
                            type=str,help="shapefile location")

    # only required when shapefile contains multiple record
    arg_parser.add_argument('-sp', '--shapefile-prop', dest="shpprop", default=None,
                            type=str,help="csv header if shapefile contains multiple records")

    arg_parser.add_argument('-r', '--reducer',dest="reducer",
                            type=str,default='avg',    help="reducer min,max,avg,wavg")

    arg_parser.add_argument('-o', '--output',    dest="out", required=True,
                            type=str,default='ts.csv' ,help="output file")

    args = arg_parser.parse_args()



    nci={}
    
    for rec in args.nci.split(';'):
        rec_split = rec.split('=')
        
        if len(rec_split)!=2 or rec_split[1]=='': 
            continue

        key,val=rec_split
        nci[key]=val


    if args.shp.endswith('.zip'):
        args.shp='zip://'+args.shp


    # read netcdf

    nc_file = Dataset(args.nc,'r')
    lats    = nc_file.variables[nci['Y']][:]
    lons    = nc_file.variables[nci['X']][:]
    datavar = nc_file.variables[nci['V']][:]
    timevar = nc_file.variables[nci['T']]

    # [parse time]

    times  = num2date(timevar[:],timevar.units)
    times = [ tx.strftime(tx.format) for tx in times  ]

    tseries_data = pd.DataFrame()
    tseries_data['date']=times

    # if lat and lon position is reversed transpose
    transpose_weight=False

    dims=nc_file.variables[nci['V']].dimensions

    # [check dimesnion order]
    t_pos,y_pos,x_pos = dims.index(nci['T']),dims.index(nci['Y']),dims.index(nci['X'])

    if not ( (t_pos<y_pos<x_pos) or (t_pos<x_pos<y_pos) ):
        sys.exit('invalid time dimension orders')
    
    if y_pos>x_pos:
        transpose_weight=True
        print('weight needs to be transposed')

    # if datavar is not masked array create masked array
    

    if nci.get('slicer',None)!=None:

        try:
            datavar = eval(f"datavar{nci['slicer']}")
        except:
            sys.exit('invalid slicing information')

    if len(datavar.shape)>3:

        sys.exit(f"{nci['V']} has more than 3 dimension,provide slicing information")


    # read shapefile

    shp_file = fiona.open(args.shp,'r')

    use_prop_header=False

    if len(shp_file)>1:
        use_prop_header=True

        if args.shpprop==None:
            sys.exit(
                'shapefile has more than 1 record.',
                'No shape properties is provided for column header'
            )

    premasked=np.ma.is_masked(datavar)

    if premasked:
        # explicitly copy this mask otherwise gets 
        # overwriten at every iteration of shape

        root_mask=datavar.mask.copy()

    # extract data
    for rec in tqdm(shp_file):
        tseries_val=[None]*len(times)
        
        shapely_obj = shape(rec['geometry']) 

        # get weighted grid
        pys = scissor(shapely_obj,lats,lons)
        weight_grid = pys.get_masked_weight()

        # handle premasked values 
        if premasked:
            datavar.mask=np.bitwise_or(root_mask,weight_grid.mask)
        else:
            datavar.mask=weight_grid.mask
        
        if use_prop_header:
            header=''
            for prop in args.shpprop.split(';'):
                header += str(rec['properties'].get(prop,''))+','
        else:
            header = nci['V']

        for ti in range(len(times)):

            if args.reducer=='min':

                tseries_val[ti] = datavar[ti].min()

            elif args.reducer=='max':

                tseries_val[ti] = datavar[ti].max()

            elif args.reducer=='avg':

                tseries_val[ti] = datavar[ti].mean()

            elif args.reducer=='wavg':

                tseries_val[ti] = np.average(datavar[ti],weights=weight_grid)

        tseries_data[header] = tseries_val

        if not args.out.endswith('.csv'):
            args.out+='.csv'
        tseries_data.to_csv(args.out)






if __name__ == '__main__':
    main()