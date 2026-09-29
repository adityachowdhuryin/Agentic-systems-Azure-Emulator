param location string = 'eastus2'
// eastus2 sometimes blocks new SQL servers; use eastus (RG region) by default
param sqlLocation string = 'eastus'
param namePrefix string = 'asl-invoice'
param sqlAdminLogin string = 'asladmin'
@secure()
param sqlAdminPassword string
param foundryAccountName string = 'anujthakur-3048-resource'
param acrName string = 'aslinvoiceacr'
param serviceBusName string = 'aslinvoicebus'
param sqlServerName string = 'asl-invoice-sql01'

var tags = {
  project: 'asl-invoice'
  costCenter: 'lab'
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: '${namePrefix}-logs'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${namePrefix}-appi'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  // Storage names: 3-24 chars, lowercase alphanumeric only
  name: take('aslinv${uniqueString(resourceGroup().id)}', 24)
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
  }
}

resource blobServices 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storage
  name: 'default'
}

resource documentsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobServices
  name: 'documents'
  properties: { publicAccess: 'None' }
}

resource sb 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: serviceBusName
  location: location
  tags: tags
  sku: {
    name: 'Basic'
    tier: 'Basic'
  }
}

resource invoiceQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: sb
  name: 'invoice-review'
  properties: {
    deadLetteringOnMessageExpiration: true
    maxDeliveryCount: 5
  }
}

resource salesQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: sb
  name: 'sales-lead-qualification'
  properties: {
    deadLetteringOnMessageExpiration: true
    maxDeliveryCount: 5
  }
}

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: take('${namePrefix}-kv${uniqueString(resourceGroup().id)}', 24)
  location: location
  tags: tags
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
  }
}

resource sqlServer 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: sqlServerName
  location: sqlLocation
  tags: tags
  properties: {
    administratorLogin: sqlAdminLogin
    administratorLoginPassword: sqlAdminPassword
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
  }
}

resource sqlFw 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = {
  parent: sqlServer
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

resource sqlDb 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  parent: sqlServer
  name: 'asl_invoice'
  location: sqlLocation
  tags: tags
  sku: {
    name: 'Basic'
    tier: 'Basic'
    capacity: 5
  }
  properties: {
    collation: 'SQL_Latin1_General_CP1_CI_AS'
  }
}

resource cae 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: '${namePrefix}-cae'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

resource mi 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-mi'
  location: location
  tags: tags
}

// Role assignments require User Access Administrator on the RG.
// After deploy, Anuj (or UAA) should run azure/infra/assign-roles.sh

output acrLoginServer string = acr.properties.loginServer
output storageAccountName string = storage.name
output serviceBusNamespace string = sb.name
output serviceBusFqdn string = '${sb.name}.servicebus.windows.net'
output sqlServerFqdn string = sqlServer.properties.fullyQualifiedDomainName
output sqlDatabaseName string = sqlDb.name
output keyVaultName string = kv.name
output keyVaultUri string = kv.properties.vaultUri
output containerAppsEnvId string = cae.id
output managedIdentityId string = mi.id
output managedIdentityClientId string = mi.properties.clientId
output appInsightsConnectionString string = appInsights.properties.ConnectionString
output foundryAccountName string = foundryAccountName
output managedIdentityPrincipalId string = mi.properties.principalId
