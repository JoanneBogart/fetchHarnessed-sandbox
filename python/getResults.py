import sqlalchemy
import collections
import operator
import string

# Prune list of dicts.  If key is in the dict and value is not
# equal to supplied value, discard
def pruneInstances(k, v, instances):
    if k not in instances[0].keys(): return
    ix = len(instances) - 1
    while ix > 0:
        if instances[ix][k] != v:
            del instances[ix]
        ix -= 1
    return

def _verifyRun(run):
    try:
        intRun = int(run)
    except ValueError:
        try:
            intRun = int(run[:-1])
        except ValueError:
            raise
    return intRun

def  _storePaths(results, pathlist):
    row = results.fetchone()
    if (row == None):
        raise Exception("No rows found")

    aid = row['aid']
    while (row != None):
        if row['aid'] != aid: 
            #print "Done since new activity id not equal to old"
            #print "Old: ", aid, " New: ", row['aid'] 
            break          # we're done
        pathlist.append(row['vp'])
        row = results.fetchone()

class getResults():
    def __init__(self, dbConnectFile='db_connect.txt'):
        self.engine = None
        self.dbConnectFile = dbConnectFile

    # Clear everything except connect file parameter
    def _clearCache(self) :
        self.htype = None
        self.model = None
        self.experimentSN = None
        self.hardwareLabel = None
        self.travelerName = None
        self.schemaName = None
        self.runLabel = None
        self.itemFilter = None
        self.intRun = None
        self.hardwareDict = None

    def connectDB(self):
        print 'dbConnect file is ', self.dbConnectFile
        kwds = {}
        try:
            with open(self.dbConnectFile) as f:
                for line in f:
                    (key, val) = line.split()
                    kwds[key] = val
        except IOError:
            raise IOError, "Unable to open db connect file" + self.dbConnectFile

        # Create a new mysql connection object.
        db_url = sqlalchemy.engine.url.URL('mysql+mysqldb', **kwds)
        self.engine = sqlalchemy.create_engine(db_url)
        #mysql_connection = engine.raw_connection()   apparently unused

        print 'connected to host' , kwds['host']


    def getResultsJH(self, htype=None, model=None,
                     experimentSN=None, hardwareLabel=None, travelerName=None,
                     schemaName=None, itemFilter=None, runLabel=None):
        self._clearCache();
        self.htype = htype
        self.model = model
        self.experimentSN = experimentSN
        self.hardwareLabel = hardwareLabel
        self.travelerName = travelerName
        self.schemaName = schemaName
        self.itemFilter=itemFilter
        self.runLabel = runLabel

        self._verifyParameters()

	# Form list of hardware ids for components of interest
        hids = []
        hids_str = []
        hidQuery = "select H2.id as hid2 from Hardware H2 join HardwareType HT on H2.hardwareTypeId=HT.id where HT.name='" + self.htype + "'"
        if self.experimentSN is not None:
            hidQuery += " and H2.lsstId='" + self.experimentSN + "'"

        elif self.model is not None:    
            hidQuery += "and H2.model='" + self.model + "'"

        # To support hardware label arg, add extra condition to where clause
        # but not for this first attempt

        # Retrieve list of all rootActivityId's which may be relevant
        # (correct process name; run on a component we care about)
        rootsQuery = "select A.id as Aid, H.id as Hid, H.lsstId as expSN from Hardware H join Activity A on H.id=A.hardwareId join Process P on A.processId=P.id where H.id in (" + hidQuery + ") and A.id=A.rootActivityId and P.name='" + self.travelerName + "' order by H.id asc, A.id desc"

        #print "Query to find traveler root ids of interest\n"
        #print rootsQuery, "\n"
        result = self.engine.execute(rootsQuery)

        # Make dict associating Hid and expSN and list of root id's of interest
        raiList = []
        self.hardwareDict = {}
        for row in result:
            #print "hid=",row['Hid']," rootId=",row['Aid']
            raiList.append(str(row['Aid']))
            self.hardwareDict[row['Hid']] = row['expSN']

        result.close()

        if len(raiList) == 0:
            print "No results meeting criteria"
            exit(0)
        
        # Form list of interesting rootId's
        raiString = "('" + string.join(raiList, "','") + "')"
        #print "raiString: ", raiString, "\n"
            
        genQuery = "select {abbr}.name as resname,{abbr}.value as resvalue,{abbr}.schemaInstance as ressI,A.id as aid,Process.name as pname,A.rootActivityId as raid, A.hardwareId as hid,A.processId as pid,ASH.activityStatusId as actStatus from {resultsTable} {abbr} join Activity A on {abbr}.activityId=A.id join ActivityStatusHistory ASH on A.id=ASH.activityId join Process on Process.id=A.processId where {abbr}.schemaName='"
        genQuery += self.schemaName
        genQuery += "' and A.rootActivityId in " + raiString + " and ASH.activityStatusId='1' order by A.hardwareId asc, A.rootActivityId desc, A.processId asc, A.id desc, ressI asc, resname"
        floatQuery = genQuery.format(abbr='FRH', 
                                     resultsTable='FloatResultHarnessed')
        intQuery = genQuery.format(abbr='IRH', 
                                   resultsTable='IntResultHarnessed')
        stringQuery = genQuery.format(abbr='SRH', 
                                      resultsTable='StringResultHarnessed')

        #print "Monster float query:\n"
        #print floatQuery

        self.returnData = {}

        fresult = self.engine.execute(floatQuery)

        self._storeLastRun(fresult, 'float')

        iresult = self.engine.execute(intQuery)
        self._storeLastRun(iresult, 'int')

        sresult = self.engine.execute(stringQuery)
        self._storeLastRun(sresult, 'str')

        if self.itemFilter is not None:
            self._prune( )

        return self.returnData

    # Public routine: get results for a known run
    def getRunResults(self, run, schemaName=None, itemFilter=None):
        self._clearCache()
        if schemaName == None:
            print "Schema name required for this version of getRunResults"
            print "Have a nice day"
        if run == None:
            print "Run number is a required argument for getRunResults"
            print "Have a nice day"
        
        self.schemaName = schemaName
        self.itemFilter = itemFilter

        #try:
        #    intRun = int(run)
        #except ValueError:
        #    try:
        #        intRun = int(run[:-1])
        #    except ValueError:
        #        raise

        intRun = _verifyRun(run)
        self.intRun = intRun
        if (itemFilter != None):
            self._parseItemFilter()

        sqlString = "select RunNumber.rootActivityId as rai, Activity.hardwareId as hid, Hardware.lsstId as expSN, HardwareType.name as hname from RunNumber join Activity on RunNumber.rootActivityId=Activity.id join Hardware on Activity.hardwareId=Hardware.id join HardwareType on HardwareType.id=Hardware.hardwareTypeId where runInt='" + str(intRun) + "'";

        result = self.engine.execute(sqlString)
        for row in result:      # can only be one
            self.htype = row['hname']
            self.experimentSN = row['expSN']
            self.oneRai = row['rai']
            self.oneHid = row['hid']

        genQuery = "select {abbr}.name as resname,{abbr}.value as resvalue,{abbr}.schemaInstance as ressI,A.id as aid,A.processId as pid,Process.name as pname,ASH.activityStatusId as actStatus from {resultsTable} {abbr} join Activity A on {abbr}.activityId=A.id join ActivityStatusHistory ASH on A.id=ASH.activityId join Process on Process.id=A.processId where {abbr}.schemaName='"
        genQuery += self.schemaName
        genQuery += "' and A.rootActivityId='" + str(self.oneRai) + "' and ASH.activityStatusId='1' order by  A.id desc, ressI asc, resname"
        floatQuery = genQuery.format(abbr='FRH', 
                                     resultsTable='FloatResultHarnessed')
        intQuery = genQuery.format(abbr='IRH', 
                                   resultsTable='IntResultHarnessed')
        stringQuery = genQuery.format(abbr='SRH', 
                                      resultsTable='StringResultHarnessed')


        self.returnData = {'run' : intRun, 'raid' : self.oneRai,
                           'schemaName' : self.schemaName,
                           'experimentSN' : self.experimentSN, 
                           'hid' : self.oneHid,
                           'instances' : [{'schemaInstance' : 0}] }

        fresult = self.engine.execute(floatQuery)
        for row in fresult:
            #print " keys: ", row.keys()
            self._storeRunData(row, 'float')
        fresult.close()

        iresult = self.engine.execute(intQuery)
        for row in iresult:
            self._storeRunData(row, 'int')
        iresult.close()

        sresult = self.engine.execute(stringQuery)
        for row in sresult:
            self._storeRunData(row, 'string')
        sresult.close()

        if self.itemFilter is not None:
            pruneInstances(self.itemFilter[0], self.itemFilter[1],
                           self.returnData['instances'])
         

        return self.returnData

    # Inputs:   run (may be integer or string form, e.g. '1256D'
    #           stepName      (e.g. 'fe55_raft_analysis')
    # Someday the stepName arg. will be optional
    # Returns:
    #      A dict of lists.   Key is step name.  Value is a list of 
    #                         data catalog virtual paths for files
    #                         generated by the step. 
    def getFilepaths(self, run, stepName=None):
        intRun = _verifyRun(run)
        self.intRun = intRun

        if stepName == None:
            raise KeyError, 'stepName argument is required for othis implementation'
        q = "select F.virtualPath as vp,P.name,P.id,A.id as aid from FilepathResultHarnessed F join Activity A on F.activityId=A.id join Process P on P.id=A.processId join RunNumber on A.rootActivityId=RunNumber.rootActivityId where RunNumber.runInt='" + str(intRun)
        q += "' and P.name='" + stepName 
        q += "' order by P.id,A.id desc,F.virtualPath"

        #print "The query: "
        #print q
        results = self.engine.execute(q)
        self.returnData = {stepName : [ ]}
        _storePaths(results, self.returnData[stepName])

        return self.returnData

    def _verifyParameters(self):
        if self.htype is None:
            raise KeyError,'Missing value for "htype"'
        if self.schemaName is None:
            raise KeyError, 'Missing value for "schemaName"'
        if self.itemFilter is not None:
            self._parseItemFilter()

    def _parseItemFilter(self):
        # Must be tuple of length 2, each item a string
        if not isinstance(self.itemFilter, tuple):
            raise KeyError, 'itemFilter must be tuple'
        if not len(self.itemFilter) == 2:
            raise KeyError, 'itemFilter must be tuple of length 2'
        if not isinstance(self.itemFilter[0], str): 
            raise KeyError, 'itemFilter key must be a string'
        if isinstance(self.itemFilter[1], str) or isinstance(self.itemFilter[1], int) or isinstance(self.itemFilter[1], long): return
        raise KeyError, 'itemFilter value must be integer or string'

    # Data comes back sorted by hardware component (ascending), then run
    # (root activity id, descending) We only want data from the most
    # recent run. _storeData tells us when to move on to next component
    def _storeLastRun(self, dbresults, dtype):
        row = dbresults.fetchone()
        while (row != None):
          expSN = self.hardwareDict[row['hid']]
          oldHid = row['hid']
          iRow = 1
          while ((row != None) and (oldHid == row['hid']) ):
              more = self._storeData(expSN, row, dtype)
              if (more == 0):       # skip to next expSN
                  #print "Got more == 0 on iRow ", iRow
                  while oldHid == row['hid']:
                      row = dbresults.fetchone()
                      iRow +=1
                      if row == None: break
              else:
                  row = dbresults.fetchone()
                  iRow += 1
        #print "total # of rows: ", iRow
        dbresults.close()


    # Store a single value, creating containing dicts as needed
    # Returns 0 if new (older) root act. id was encountered, else 1
    def _storeData(self, expSN, row, dtype):
        if expSN not in self.returnData:
            self.returnData[expSN] = expDict = {}
            expDict['hid'] = row['hid']
            expDict['raid'] = row['raid']

            #  First instance record will be used for type information
            expDict['instances'] = [{'schemaInstance' : 0}]
        else : expDict = self.returnData[expSN]

        if expDict['raid'] != row['raid']:
            #print 'Discarding data from traveler with raid=', row['raid']
            #print 'after storing data for traveler with raid=', expDict['raid']
            return 0

        schemaInstance = row['ressI']
        # Note instance numbers always start with 1; list indices with 0

        # Make our instance record if it doesn't already exist
        myInstance = None
        for i in expDict['instances']:
            if i['schemaInstance'] == schemaInstance:
                myInstance = i

                if myInstance['activityId'] != row['aid']:
                    if myInstance['processId'] != row['pid']:
                        # Need another instance after all
                        myInstance = None
                    else: # Skip. > 1 activity for same step in traveler.
                        return -1
                break
        if myInstance == None:
            myInstance = {'schemaInstance' : schemaInstance}
            expDict['instances'].append(myInstance)
            myInstance['activityId']  = row['aid']
            myInstance['processId'] = row['pid']
            myInstance['processName'] = row['pname']

        if row['resname'] not in expDict['instances'][0].keys():
            expDict['instances'][0][row['resname']] = dtype
        myInstance[row['resname']] = row['resvalue']

        return 1

    # For now, just have one list of instances
    # When we handle multiple schemas in one request it will be different
    def _storeRunData(self, row, dtype):
        schemaInstance = row['ressI']
        myInstance = None
        for i in self.returnData['instances']:
            if i['schemaInstance'] == schemaInstance:
                myInstance = i

                if myInstance['activityId'] != row['aid']:
                    if myInstance['processId'] != row['pid']:
                        # Need another instance after all
                        myInstance = None
                    else: # Skip. > 1 activity for same step in traveler.
                        return -1
                break
        if myInstance == None:
            myInstance = {'schemaInstance' : schemaInstance, 
                          'processId' : row['pid'],
                          'processName' : row['pname'],
                          'activityId': row['aid']}
            self.returnData['instances'].append(myInstance)

        if row['resname'] not in self.returnData['instances'][0].keys():
            self.returnData['instances'][0][row['resname']] = dtype
        myInstance[row['resname']] = row['resvalue']
        return 1


    def _prune(self):
        if self.itemFilter is None: return
        key = self.itemFilter[0]
        val = self.itemFilter[1]
        for expSN in self.returnData:
            expDict = self.returnData[expSN]
            pruneInstances(key, val, expDict['instances'])

        
if __name__ == "__main__":
    
    #schemaName = 'read_noise'
    #htype = 'ITL-CCD'
    #travelerName = 'SR-EOT-1'

    #eT = getResults(schemaName=schemaName, htype=htype, travelerName=travelerName, experimentSN='ITL-3800C-021', dbConnectFile='/u/ey/jrb/et_prod_query.txt', itemFilter=('amp', 3))
    #eT = getResults(schemaName=schemaName, valueName=valueName, htype=htype, travelerName=travelerName, model='3800C', dbConnectFile='/u/ey/jrb/et_prod_query.txt', itemFilter=('amp' , 3) )


    eT = getResults(dbConnectFile='/u/ey/jrb/et_dev_query.txt')
    eT.connectDB()

    schemaName = 'fe55_raft_analysis'
    htype = 'LCA-11021_RTM'
    travelerName = 'SR-RTM-EOT-03'

    returnData = eT.getResultsJH(schemaName=schemaName, htype=htype, 
                                 travelerName=travelerName,
                                 experimentSN='LCA-11021_RTM-004_ETU2-Dev',
                                 itemFilter=('sensor_id', 'ITL-3800C-102-Dev'))

    for lsstId in returnData:
        print "\n\nKeys in dict for component: ",lsstId 
        expDict = returnData[lsstId]
        print "hardware id: ", returnData[lsstId]['hid']
        print "root activity id: ", returnData[lsstId]['raid']

        nInstance = len(returnData[lsstId]['instances'])
        i = 0
        for d in returnData[lsstId]['instances']:
            print "Instance #", i, " dict: ", d 
            i += 1

    runData = eT.getRunResults(4689, schemaName=schemaName,
                               itemFilter=('sensor_id', 'ITL-3800C-102-Dev'))

    for k in runData:
        if k != 'instances':
            print k,"=", runData[k]
        else: print k

    i = 0
    for d in runData['instances']:
        print "Instance #", i, " dict: ", d
        i += 1

    fileData = eT.getFilepaths('4689D', 'read_noise_raft')
    for k in fileData:
        print "step name is ", k, "Files below"
        for f in fileData[k]:
            print "   ", f
