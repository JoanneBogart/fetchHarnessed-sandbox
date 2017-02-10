import sqlalchemy
import collections
import operator
import string

class getResults():

    def __init__(self, htype=None, model=None, experimentSN=None, 
                 hardwareLabel=None, travelerName=None, stepName=None, 
                 schemaName=None, itemFilter=None, valueName=None,
                 runLabel=None, stepStatus='success', 
                 travelerStatus=None,dbConnectFile='db_connect.txt'):
        self.htype = htype
        self.model = model
        self.experimentSN = experimentSN
        self.hardwareLabel = hardwareLabel
        self.travelerName = travelerName
        self.schemaName = schemaName
        self.valueName = valueName
        self.runLabel = runLabel
        self.itemFilter = itemFilter
        self.stepStatus = stepStatus
        self.travelerStatus = travelerStatus
        self.dbConnectFile = dbConnectFile

    def setParams(self, htype=None, model=None, experimentSN=None, 
                 hardwareLabel=None, travelerName=None, stepName=None, 
                 schemaName=None, itemFilter=None, valueName=None, 
                  runLabel=None, stepStatus=None, 
                 travelerStatus=None,dbConnectFile=None):
        if htype is not None: self.htype = htype
        if model is not None: self.model = model
        if experimentSN is not None: self.experimentSN = experimentSN
        if hardwareLabel is not None: self.hardwareLabel = hardwareLabel
        if travelerName is not None: self.travelerName = travelerName
        if schemaName is not None: self.schemaName = schemaName
        if valueName is not None: self.valueName = valueName
        if runLabel is not None: self.runLabel = runLabel
        if itemFilter is not None: self.itemFilter = itemFilter
        if stepStatus is not None: self.stepStatus = stepStatus
        if travelerStatus is not None: self.travelerStatus = travelerStatus
        if dbConnectFile is not None: self.dbConnectFile = dbConnectFile

        # NOTE:  For first attempt, only use
        #     htype, dbConnectFile, schemaName
        #     travelerName if present
        #     and, if present, model and experimentSN
        #
        #     stepStatus has default value of 'success'. Does anything
        #     else ever make sense?
        #     stepName doesn't buy us much; might not implement ever

    def connectDB(self):

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
        engine = sqlalchemy.create_engine(db_url)
        mysql_connection = engine.raw_connection()

        print 'connected to host' , kwds['host']

        # Appears not to be used for anything
        #cursor = mysql_connection.cursor()

        return engine

    def getResultsJH(self,engine):
        self.verifyParameters()

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

        print "hardware query is: \n"
        print hidQuery, "\n"

        # Retrieve list of all rootActivityId's which may be relevant
        # (correct process name; run on a component we care about)
        rootsQuery = "select A.id as Aid, H.id as Hid, H.lsstId as expSN from Hardware H join Activity A on H.id=A.hardwareId join Process P on A.processId=P.id where H.id in (" + hidQuery + ") and A.id=A.rootActivityId and P.name='" + self.travelerName + "' order by H.id asc, A.id desc"

        print "Query to find traveler root ids of interest\n"
        print rootsQuery, "\n"
        result = engine.execute(rootsQuery)

        # Make dict associating Hid and expSN and list of root id's of interest
        raiList = []
        hardwareDict = {}
        for row in result:
            print "hid=",row['Hid']," rootId=",row['Aid']
            raiList.append(str(row['Aid']))
            hardwareDict[row['Hid']] = row['expSN']
        if len(raiList) == 0:
            print "No results meeting criteria"
            exit(0)
        
        # Form list of interesting rootId's
        raiString = "('" + string.join(raiList, "','") + "')"
        print "raiString: ", raiString, "\n"
            
        genQuery = "select {abbr}.name as resname,{abbr}.value as resvalue,{abbr}.schemaInstance as ressI,A.id as aid,A.rootActivityId as raid, A.hardwareId as hid,ASH.activityStatusId as actStatus from {resultsTable} {abbr} join Activity A on {abbr}.activityId=A.id join ActivityStatusHistory ASH on A.id=ASH.activityId where {abbr}.schemaName='"
        genQuery += self.schemaName
        genQuery += "' and A.rootActivityId in " + raiString + " and ASH.activityStatusId='1' order by A.hardwareId asc, A.rootActivityId desc, ressI asc, resname"
        floatQuery = genQuery.format(abbr='FRH', 
                                     resultsTable='FloatResultHarnessed')
        intQuery = genQuery.format(abbr='IRH', 
                                   resultsTable='IntResultHarnessed')
        stringQuery = genQuery.format(abbr='SRH', 
                                      resultsTable='StringResultHarnessed')

        print "Monster float query:\n"
        print floatQuery
        print "Monster int query:\n"
        print intQuery
        print "Monster string query:\n"
        print stringQuery

        self.returnData = {}

        fresult = engine.execute(floatQuery)
        #print "Found ",len(rresult), " rows"

        for row in fresult:
          rowout =  "Hid: " + str(row['hid'])+  " Aid: " + str(row['aid']) + " {abbr} instance: " + str(row['ressI']) +  " {abbr}name: " + row['resname'] + " {abbr}value: " + str(row['resvalue'])
          #print rowout.format(abbr="FRH")
          #, " Act status: ", row['actStatus']

          expSN = hardwareDict[row['hid']]
          self.storeData(expSN, row, 'float')

        iresult = engine.execute(intQuery)

        for row in iresult:
          rowout =  "Hid: " + str(row['hid'])+  " Aid: " + str(row['aid']) + " {abbr} instance: " + str(row['ressI']) +  " {abbr}name: " + row['resname'] + " {abbr}value: " + str(row['resvalue'])
          #print rowout.format(abbr="IRH")
          expSN = hardwareDict[row['hid']]
          self.storeData(expSN, row, 'int')

        sresult = engine.execute(stringQuery)
        for row in sresult:
          rowout =  "Hid: " + str(row['hid'])+  " Aid: " + str(row['aid']) + " {abbr} instance: " + str(row['ressI']) +  " {abbr}name: " + row['resname'] + " {abbr}value: " + str(row['resvalue'])
          #print rowout.format(abbr="SRH")
          expSN = hardwareDict[row['hid']]
          self.storeData(expSN, row, 'str')

        if self.itemFilter is not None:
            self.prune( )

        return self.returnData

    def verifyParameters(self):
        if self.htype is None:
            raise KeyError,'Missing value for "htype"'
        if self.schemaName is None:
            raise KeyError, 'Missing value for "schemaName"'
        if self.itemFilter is not None:
            # Must be tuple of length 2, each item a string
            if not isinstance(self.itemFilter, tuple):
                raise KeyError, 'itemFilter must be tuple'
            if not len(self.itemFilter) == 2:
                raise KeyError, 'itemFilter must be tuple of length 2'
            if not isinstance(self.itemFilter[0], str): 
                raise KeyError, 'itemFilter key must be a string'
            if isinstance(self.itemFilter[1], str) or isinstance(self.itemFilter[1], int) or isinstance(self.itemFilter[1], long): return
            raise KeyError, 'itemFilter value must be integer or string'

    # Store a single value, creating containing dicts as needed
    def storeData(self, expSN, row, dtype):
        if expSN not in self.returnData:
            self.returnData[expSN] = expDict = {}
            expDict['hid'] = row['hid']
            expDict['aid'] = row['aid']
            expDict['raid'] = row['raid']

            #  First instance record will be used for type information
            expDict['instances'] = [{'instanceNumber' : 0}]
        else : expDict = self.returnData[expSN]

        instanceNumber = row['ressI']
        # Note instance numbers always start with 1; list indices with 0

        # Make our instance record if it doesn't already exist
        myInstance = None
        for i in expDict['instances']:
            if i['instanceNumber'] == instanceNumber:
                myInstance = i
                break
        if myInstance == None:
            myInstance = {'instanceNumber' : instanceNumber}
            expDict['instances'].append(myInstance)

        if row['resname'] not in expDict['instances'][0].keys():
            expDict['instances'][0][row['resname']] = dtype
        myInstance[row['resname']] = row['resvalue']

    def prune(self):
        if self.itemFilter is None: return
        key = self.itemFilter[0]
        val = self.itemFilter[1]
        for expSN in self.returnData:
            expDict = self.returnData[expSN]
            if key not in expDict['instances'][0].keys(): return
            ix = len(expDict['instances']) - 1
            while ix > 0:
                if expDict['instances'][ix][key] != val:
                    del expDict['instances'][ix]
                ix -= 1

if __name__ == "__main__":
    
    schemaName = 'read_noise'
    valueName = 'read_noise'
    htype = 'ITL-CCD'
    travelerName = 'SR-EOT-1'

    #eT = getResults(schemaName=schemaName, valueName=valueName, htype=htype, travelerName=travelerName, experimentSN='ITL-3800C-021', dbConnectFile='/u/ey/jrb/et_prod_query.txt', itemFilter=('amp', 3))
    eT = getResults(schemaName=schemaName, valueName=valueName, htype=htype, travelerName=travelerName, model='3800C', dbConnectFile='/u/ey/jrb/et_prod_query.txt', itemFilter=('amp' , 3) )

    engine = eT.connectDB()

    returnData  = eT.getResultsJH(engine)
    for lsstId in returnData:
        print "\n\nKeys in dict for component: ",lsstId 
        expDict = returnData[lsstId]
        print "hardware id: ", returnData[lsstId]['hid']
        print "root activity id: ", returnData[lsstId]['raid']
        print "activity id: ", returnData[lsstId]['aid']

        nInstance = len(returnData[lsstId]['instances'])
        i = 0
        for d in returnData[lsstId]['instances']:
            print "Instance #", i, " dict: ", d 
            i += 1

