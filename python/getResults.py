import sqlalchemy
import collections
import operator
import string

#  Private static functions
# Prune list of dicts.  If key is in the dict and value is not
# equal to supplied value, discard
def _pruneInstances(k, v, instances):
    if k not in instances[0].keys(): return

    ix = len(instances) - 1
    while ix > 0:
        if instances[ix][k] != v:
            del instances[ix]
        ix -= 1
    return

def _pruneRun(k, v, stepDict):
    for step in stepDict:
        #print "Pruning for step ",step
        schdict = stepDict[step]
        for schname in schdict:
            #print "Pruning schema ", schname
            _pruneInstances(k, v, schdict[schname])

def _verifyRun(run):
    try:
        intRun = int(run)
    except ValueError:
        try:
            intRun = int(run[:-1])
        except ValueError:
            raise
    return intRun

def  _storePaths(results, stepmap):
    row = results.fetchone()
    if (row == None):
        raise Exception("No rows found")

    aid = 0
    pid = 0

    while (row != None):
        if pid != row['pid']:       # need new map entry
            #print "Create new entry for new pid, pname", row['pid'], " ",row['pname'] 
            pid = row['pid']
            ourList = []
            stepmap[row['pname']] = ourList
            aid = row['aid']
            #print "aid is ", row['aid']
        while ((aid != row['aid']) and  (pid == row['pid'])):
            row = results.fetchone()
            if row == None: return
        if (pid == row['pid']):
            ourList.append(row['vp'])
            row = results.fetchone()
        else:
           "Got to new pid ", row['pid']
    return

_statusJoins = "join ActivityStatusHistory ASH on A.id=ASH.activityId join ActivityFinalStatus on ActivityFinalStatus.id=ASH.activityStatusId";
_successCondition = "ActivityFinalStatus.name='success'"


class getResults():
    # Normally want data only from activities with good status. 
    # Assume Activity is aliased as A

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
        self.returnData = None

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
        rootsQuery = "select A.id as Aid, H.id as Hid, H.lsstId as expSN, RunNumber.runNumber as runString,RunNumber.runInt as runInt  from Hardware H join Activity A on H.id=A.hardwareId join Process P on A.processId=P.id join RunNumber on RunNumber.rootActivityId=A.rootActivityId where H.id in (" + hidQuery + ") and A.id=A.rootActivityId and P.name='" + self.travelerName + "' order by H.id asc, A.id desc"

        #print "Query to find traveler root ids of interest\n"
        #print rootsQuery, "\n"
        result = self.engine.execute(rootsQuery)

        # Make dict associating Hid and expSN and list of root id's of interest
        raiList = []
        self.hardwareDict = {}
        self.runDict = {}
        for row in result:
            #print "hid=",row['Hid']," rootId=",row['Aid']
            raiList.append(str(row['Aid']))
            self.hardwareDict[row['Hid']] = row['expSN']
            self.runDict[row['Aid']] = {'runString' : row['runString'], 'runInt' : row['runInt']}

        result.close()

        if len(raiList) == 0:
            print "No results meeting criteria"
            exit(0)
        
        # Form list of interesting rootId's
        raiString = "('" + string.join(raiList, "','") + "')"
        #print "raiString: ", raiString, "\n"
            
        genQuery = "select {abbr}.name as resname,{abbr}.value as resvalue,{abbr}.schemaInstance as ressI,{abbr}.schemaname as schname, A.id as aid,Process.name as pname,A.rootActivityId as raid, A.hardwareId as hid,A.processId as pid,ASH.activityStatusId as actStatus from {resultsTable} {abbr} join Activity A on {abbr}.activityId=A.id "
        genQuery += _statusJoins;
        genQuery += " join Process on Process.id=A.processId where {abbr}.schemaName='"
        genQuery += self.schemaName
        genQuery += "' and A.rootActivityId in " + raiString + " and "
        genQuery += _successCondition
        genQuery += " order by A.hardwareId asc, A.rootActivityId desc, pid asc, schname, A.id desc, ressI asc, resname"
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

        self._storeForJH(fresult, 'float')

        iresult = self.engine.execute(intQuery)
        self._storeForJH(iresult, 'int')

        sresult = self.engine.execute(stringQuery)
        self._storeForJH(sresult, 'string')

        if self.itemFilter is not None:
            self._prune( )

        return self.returnData

    # Public routine: get results for a known run
    def getRunResults(self, run, schemaName=None, itemFilter=None):
        self._clearCache()
        if run == None:
            print "Run number is a required argument for getRunResults"
            print "Have a nice day"
        
        self.schemaName = schemaName
        self.itemFilter = itemFilter

        intRun = _verifyRun(run)
        self.intRun = intRun
        if (itemFilter != None):
            self._parseItemFilter()
        
        sqlString = "select RunNumber.rootActivityId as rai,RunNumber.runNumber as runString, Activity.hardwareId as hid, Hardware.lsstId as expSN, HardwareType.name as hname from RunNumber join Activity on RunNumber.rootActivityId=Activity.id join Hardware on Activity.hardwareId=Hardware.id join HardwareType on HardwareType.id=Hardware.hardwareTypeId where runInt='" + str(intRun) + "'";

        result = self.engine.execute(sqlString)
        for row in result:      # can only be one
            self.htype = row['hname']
            self.experimentSN = row['expSN']
            self.oneRai = row['rai']
            self.oneHid = row['hid']

        genQuery = "select {abbr}.schemaName as schname,{abbr}.name as resname,{abbr}.value as resvalue,{abbr}.schemaInstance as ressI,A.id as aid,A.processId as pid,Process.name as pname,ASH.activityStatusId as actStatus from {resultsTable} {abbr} join Activity A on {abbr}.activityId=A.id " + _statusJoins + " join Process on Process.id=A.processId where ";
        if self.schemaName != None:
            genQuery += "{abbr}.schemaName='"
            genQuery += self.schemaName
            genQuery += "' and "
        genQuery += "A.rootActivityId='" + str(self.oneRai) + "' and " + _successCondition + " order by  pid asc,schname,A.id desc, ressI asc, resname"
        floatQuery = genQuery.format(abbr='FRH', 
                                     resultsTable='FloatResultHarnessed')
        intQuery = genQuery.format(abbr='IRH', 
                                   resultsTable='IntResultHarnessed')
        stringQuery = genQuery.format(abbr='SRH', 
                                      resultsTable='StringResultHarnessed')

        
        self.returnData = {'run' : intRun, 'raid' : self.oneRai,
                           'experimentSN' : self.experimentSN, 
                           'hid' : self.oneHid,
                           'steps' : {} }
        
        fresult = self.engine.execute(floatQuery)
        self._storeRunAll(self.returnData['steps'], fresult, 'float', 0)
        fresult.close()
        
        iresult = self.engine.execute(intQuery)
        self._storeRunAll(self.returnData['steps'], iresult, 'int', 0)
        iresult.close()
        
        sresult = self.engine.execute(stringQuery)
        self._storeRunAll(self.returnData['steps'], sresult, 'string', 0)
        sresult.close()

        if self.itemFilter is not None:
            _pruneRun(self.itemFilter[0], self.itemFilter[1],  
                      self.returnData['steps'])
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

        q = "select F.virtualPath as vp,P.name as pname,P.id as pid,A.id as aid from FilepathResultHarnessed F join Activity A on F.activityId=A.id " + _statusJoins + " join Process P on P.id=A.processId join RunNumber on A.rootActivityId=RunNumber.rootActivityId where RunNumber.runInt='" + str(intRun)
        q += "' and " + _successCondition
        if stepName != None:
            q += " and P.name='" + stepName + "' "
        q += " order by P.id,A.id desc,F.virtualPath"
        
        #print "\nThe query for getFilepaths: "
        #print q
        #print "\n"
        results = self.engine.execute(q)
        self.returnData = {}
        _storePaths(results, self.returnData)

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


    # Currently this routine only can be called from getRunResults.
    # It needs to know more to know when to stop for multi-component (hence multi-run)
    # data
    def _storeRunAll(self, stepDicts, dbresults, dtype, hid, row=None):
        if row==None: row = dbresults.fetchone()
        pname = ""
        schname = ""
        if hid > 0: raid = row['raid']
        else: raid = 0

        while row != None:
            if raid > 0:
                if row['raid'] != raid:
                    while row['hid'] == hid:
                        row = dbresults.fetchone()
                        if row == None: return None

            if pname != row['pname']:
                pname = row['pname']
                if pname in stepDicts: pdict = stepDicts[pname]
                else: 
                    pdict = {}
                    stepDicts[pname] = pdict
                schname=""
            if schname != row['schname']:
                schname = row['schname']
                if schname in pdict: ilist = pdict[schname]
                else:
                    ilist = [{'schemaInstance':0}]
                    pdict[schname] = ilist
            row = self._storeOne(ilist, dbresults, row, dtype)   
            if hid > 0:
                if row == None: return None
                if row['hid'] != hid: return row

        return row
    
    def _storeOne(self, ilist, dbresults, row, dtype):
        instanceNum = row['ressI']
        myInstance = None
        for instance in ilist:
            if instance['schemaInstance'] == instanceNum:
                myInstance = ilist[instanceNum]
                if myInstance['activityId'] != row['aid']:
                    thisAid = row['aid']
                    while thisAid == row['aid']:
                        row = dbresults.fetchone()
                        if row == None: return None
                    return row
                break

        if myInstance == None:
            myInstance = {"schemaInstance": instanceNum, "activityId":row['aid']}
            ilist.append(myInstance)

        ilist[0][row['resname']] = dtype;
        myInstance[row['resname']] = row['resvalue']
        return dbresults.fetchone()

    def _storeForJH(self, dbresults, dtype):
        row = dbresults.fetchone()
        if row==None: return

        while (row != None):
            hid = row['hid']
            expSN = self.hardwareDict[hid]
            if expSN in self.returnData:
                expDict = self.returnData[expSN]
            else:
                expDict = {'hid' : hid, 'raid' : row['raid'],
                          'runString' : self.runDict[row['raid']]['runString'],
                          'runInt' : self.runDict[row['raid']]['runInt'],
                          'steps' : {}}
                self.returnData[expSN] = expDict
            stepDict = expDict['steps']
                
            row = self._storeRunAll(stepDict, dbresults, dtype, hid, row)

    def _prune(self):
        if self.itemFilter is None: return
        key = self.itemFilter[0]
        val = self.itemFilter[1]
        for expSN in self.returnData:
            expDict = self.returnData[expSN]
            _pruneRun(key, val, expDict['steps'])

        
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
    experimentSN='LCA-11021_RTM-004_ETU2-Dev'

    print "Calling getResultsJH with arguments"
    print "schemaName=",schemaName
    print "htype=",htype
    print "experimentSN=",experimentSN
    print "itemFilter=('sensor_id', 'ITL-3800C-102-Dev')"    
    #print "itemFilter not supplied"

    returnData = eT.getResultsJH(schemaName=schemaName, htype=htype, 
                                 travelerName=travelerName,
                                 experimentSN=experimentSN,
                                 itemFilter=('sensor_id', 'ITL-3800C-102-Dev'))

    for lsstId in returnData:
        print "\n\nKeys in dict for component: ",lsstId 
        expDict = returnData[lsstId]
        for k in expDict:
            if k != 'steps':
                print k, " : ", expDict[k]

        nSteps = len(expDict['steps'])
        print "Includes data for ", nSteps, " steps"
        for step in expDict['steps']:
            print "step name: ", step
            stepDict = expDict['steps'][step]
            for sch in stepDict:
                schemaList = stepDict[sch]
                "Found ", len(schemaList), " instances for schema ", sch
                for inst in schemaList:
                    print inst
        
    print '\n*******\n\n'
    print 'Calling getRunResults with arguments '
    print 'run=', 4689
    print 'schemaName=None'
    print "ItemFilter not suplied"
    #print "itemFilter=('sensor_id', 'ITL-3800C-102-Dev')"
    runData = eT.getRunResults(4689, schemaName=None)
                               #itemFilter=('sensor_id', 'ITL-3800C-102-Dev'))

    print '\n-----\n'
    print 'Output has these simple keys: '
    for k in runData:
        if k != 'steps':
            print k,"=", runData[k]

    print "\n"
    for step in runData['steps']:
        schdict = runData['steps'][step]
        print '\n\nStep name  ', step, 'has schema keys', schdict.keys()
        for sch in schdict:
            print 'Schema ', sch
            for instance in schdict[sch]:
                print "  ",instance


    print "Calling getFilepaths for run 4689D step name fe55_raft_analysis"
    fileData = eT.getFilepaths('4689D', 'fe55_raft_analysis')
    for k in fileData:
        print "step name is ", k, "Files below"
        for f in fileData[k]:
            print "   ", f

    print "Calling getFilepaths for run 4689D, no step name specified"
    fileData = eT.getFilepaths('4689D')
    for k in fileData:
        print "step name is ", k, "Files below"
        for f in fileData[k]:
            print "   ", f
