"""
Created on Tue Nov  4 13:44:37 2025

@author: nmp-Nakazima
Aude

Plots experiments from a material individually (regardless of the repeats, except if the Marciniak predeformation is the same) and compares it with the Nakazima (40mm) FLD

"""

import numpy as np
import matplotlib.pyplot as plt
import os
import pandas as pd

def plot(material, method):
    '''
    Parameters
    ----------
    material : str

    Returns
    -------
    None.
    
    Plots the Nakazima (40mm) FLD of the material (exported from the classic GUI_FLD-evaluation code)
    as well as the strainpaths of individual experiments of that same material with their necking points.
    The necking points are determined by the DIN lines method. If you want the Volk&Hora method, modify the value of "method" in the code
    
    The experiments to plot are determined by the file 'configurations_to_plot.txt' in the material folder
    (the file is manually updated by the user).
    
    /!\ The data for the Nakazima FLD is in files named 'FLD-ISO12004.txt' and 'FLD-time_dependent'
    (needs to be named 'FLD' in the GUI_FLD-evaluation pop-up window, and saved in the configuration folder)

    '''
    #choosing the postprocessing method : 0 for ISO, 1 for Volk&Hora
    if method==0:
        method='DIN average'
    elif method==1:
        method='Volk&Hora'
    
            
    
    #FLD Nakazima set with small hemispherical punch
    e_1_2=[]
    path_material = f'D:/Results/{material}'
    #reading the data file
    if method=='DIN average':
        file_name='FLD-ISO12004'
    elif method=='Volk&Hora':
        file_name='FLD-time_dependent'
    with open(f'{path_material}/E0_RM00_005/{file_name}.txt', 'r') as fld_naka:
        values = fld_naka.readlines()[1].split(',')
    #only taking the interesting data from the file
    for i in range(len(values)):
        if i%2==1: 
            e_1_2.append(values[i])
    e1_naka, e2_naka = [], []
    for i in range(len(e_1_2)):
        if i%2==0:
            e1_naka.append(float(e_1_2[i]))
        else:
            e2_naka.append(float(e_1_2[i]))
    #plotting the FLD
    plt.plot(e2_naka, e1_naka, '-x', linewidth=2, label='Nakazima with 40mm punch') 
    
    #getting the names of the configurations to plot
    with open(f'{path_material}/configurations_to_plot.txt', 'r') as configs:
        list_config = configs.read().splitlines()


    #these numbers will be used later to select the correct data in the strainpath files
    if method=='DIN average':
        nb1=-3
        nb2=-2
    elif method=='Volk&Hora':
        nb1=5
        nb2=6


    #getting the strainpaths of those configurations
    e1_maxs,e2_maxs,e2_mins=[max(e1_naka)],[max(e2_naka)],[min(e2_naka)] #will contain the extreme values of e1 and e2 on the plot (to set the axis limits)
    first_loop=True
    #browsing the different configurations
    for config in list_config:
        path_config = f'{path_material}/{config}'
        list_specimens = []
        with os.scandir(path_config) as d:
            for folder in d:
                if folder.name[0]=='W':
                    list_specimens.append(folder.name)
        #browsing each specimen of the configuration
        for specimen in list_specimens:
            path_specimen = f'{path_config}/{specimen}'
            list_repet = []
            with os.scandir(path_specimen) as d:
                for folder in d:
                    list_repet.append(folder.name)
                    
            #browsing each repetition of the same specimen
            marciniak=[] #to contain the marciniak displacement for each experiment
            repet_done=[] #to contain the experiments already seen
            for repet in list_repet:
                #getting the marciniak displacement data
                data = pd.read_csv(f'{path_specimen}/{repet}/{repet}_DataFile_ALL.txt', sep=';',index_col=False)
                marciniak.append([repet,data[' Position [mm]'].iloc[-1]])
            marciniak = pd.DataFrame(marciniak,columns=['repet','marc_displacement'])
                
            for repet in list(marciniak['repet']):
                
                if repet not in repet_done:
                
                    displacement = marciniak[ marciniak['repet']==repet ]['marc_displacement'].iloc[0]
                    test = marciniak[ marciniak['marc_displacement']==displacement ]
                    
                    #if the experiment is the only one with that marciniak displacement : getting the data individually
                    if len(test.values.tolist())==1:
                        with open(f'{path_specimen}/{repet}/Results/{repet}_strainpath.txt') as strainpath:
                            imgs_strainpath = strainpath.read().splitlines()
                            tab_strainpath=[]
                            for img in imgs_strainpath:
                                tab_strainpath.append(img.split(','))
                            e1=[]
                            e2=[]
                            for i in range(1,len(tab_strainpath)-1):
                                e1.append(float(tab_strainpath[i][nb1]))
                                e2.append(float(tab_strainpath[i][nb2]))
                        
                        #getting the necking point
                        df = pd.read_csv(f'{path_material}/all_results_{material}.txt', sep=',', header=0)
                        e1_necking = df[ df['Experiment name']==repet ][f'{method} e1']
                        e2_necking = df[ df['Experiment name']==repet ][f'{method} e2']
                        
                        #getting the necking point of the first corresponding marciniak experiment
                        marc_experiment = f'{config[:-1]}7_{specimen}_001'
                        e1_marc = df[ df['Experiment name']==marc_experiment ][f'{method} e1']
                        e2_marc = df[ df['Experiment name']==marc_experiment ][f'{method} e2']
                        
                        #plotting if usable
                        if float(df[ df['Experiment name']==repet ]['usable'])==1:
                            line, = plt.plot(e2,e1,'-',linewidth=0.5,label=f'{repet}')
                            plt.scatter(e2_necking, e1_necking, c=line.get_color(), marker='+', zorder=9999)
                            
                            plt.scatter(e2_marc, e1_marc, c=line.get_color(), marker='x', zorder=9998)
                            
                            #updating the future axis parameters
                            e1_maxs.append(max(e1))
                            e2_maxs.append(max(e2))
                            e2_mins.append(min(e2))
                        
                    
                    #if there are identical repetitions
                    else:
                        values={'e1':[],'e2':[],'strainpath':[]} #will contain the data of each of those repetitions
                        bool=True
                        for sublist in test.values.tolist():
                            exp = sublist[0]
                            #getting the data
                            with open(f'{path_specimen}/{exp}/Results/{exp}_strainpath.txt') as strainpath:
                                imgs_strainpath = strainpath.read().splitlines()
                                tab_strainpath=[]
                                for img in imgs_strainpath:
                                    tab_strainpath.append(img.split(','))
                                e1=[]
                                e2=[]
                                for i in range(1,len(tab_strainpath)-1):
                                    e1.append(float(tab_strainpath[i][nb1]))
                                    e2.append(float(tab_strainpath[i][nb2]))
                            e1_maxs.append(max(e1))
                            e2_maxs.append(max(e2))
                            e2_mins.append(min(e2))
                            df = pd.read_csv(f'{path_material}/all_results_{material}.txt', sep=',', header=0)
                            e1_necking = df[ df['Experiment name']==exp ][f'{method} e1']
                            e2_necking = df[ df['Experiment name']==exp ][f'{method} e2']
                            marc_experiment = f'{config[:-1]}7_{specimen}_001'
                            e1_marc = df[ df['Experiment name']==marc_experiment ][f'{method} e1']
                            e2_marc = df[ df['Experiment name']==marc_experiment ][f'{method} e2']
                            
                            #if usable, adding the data to the global dictionary
                            if float(df[ df['Experiment name']==exp ]['usable'])==1:
                                values['e1'].append(e1_necking)
                                values['e2'].append(e2_necking)
                        
                                if not bool:
                                    plt.plot(e2,e1,'-',linewidth=0.5,c=line.get_color())
                                else:
                                    line, = plt.plot(e2,e1,'-',linewidth=0.5,label=f'{exp[:-4]}')
                                    bool=False
                            
                            #updates list to remove the experiments that have already been dealt with
                            repet_done.append(exp)
                            
                            
                        #the plotted necking is the average of the neckings of all identical repetitions
                        if len(values['e1'])!=0 and len(values['e2'])!=0:
                            plt.scatter(np.nanmean(values['e2']), np.nanmean(values['e1']), c=line.get_color(), marker='+', zorder=9999)
                            plt.scatter(e2_marc, e1_marc, c=line.get_color(), marker='x', zorder=9998)
                        
                    
                    #updating the legend only once (the first time)
                    if first_loop:
                        plt.scatter([], [], c='k', marker='+', label='necking point')
                        plt.scatter([], [], c='k', marker='x', label='marciniak necking point')
                        first_loop=False
    
    #plot parameters
    plt.axvline(0, linewidth=0.5, color='k', zorder=0)
    plt.title(f'{material}: {method}', fontsize=16, fontweight='bold')
    plt.xlabel(r'Minor strain $e_2$ [$-$]')
    plt.ylabel(r'Major strain $e_1$ [$-$]')
    plt.ylim(bottom=0,top=max(e1_maxs)+0.025)
    plt.xlim(left=min(e2_mins)-0.025,right=max(e2_maxs)+0.025)
    plt.legend(loc='lower center', frameon=True, ncol=3, edgecolor='k', fontsize=8, bbox_to_anchor=(0.5, -0.4))
    plt.grid(alpha=0.5, zorder=0)
    plt.show()


#material input
material=str(input('What material do you want to study?'))
method=int(input('What method do you want to use ? Press 0 for ISO12004 and 1 for Volk&Hora: '))
plot(material, method)








