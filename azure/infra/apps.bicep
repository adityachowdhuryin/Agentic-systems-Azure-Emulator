param location string = 'eastus2'
param namePrefix string = 'asl-invoice'
param containerAppsEnvId string
param managedIdentityId string
param managedIdentityClientId string
param acrLoginServer string
param bandaImage string
param bandbImage string
param mocksImage string
param mockSystemsUrl string = 'http://mocks'
@secure()
param databaseUrl string
param serviceBusFqdn string
param storageAccountName string
param foundryProjectEndpoint string
param foundryModelName string = 'gpt-5-mini'
param appInsightsConnectionString string = ''

resource mocks 'Microsoft.App/containerApps@2023-05-01' = {
  name: 'mocks'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppsEnvId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: false
        targetPort: 8090
        transport: 'http'
        allowInsecure: true
      }
      registries: [
        {
          server: acrLoginServer
          identity: managedIdentityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'mocks'
          image: mocksImage
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 1
      }
    }
  }
}

resource banda 'Microsoft.App/containerApps@2023-05-01' = {
  name: 'banda'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppsEnvId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: acrLoginServer
          identity: managedIdentityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'banda'
          image: bandaImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'DATABASE_URL', value: databaseUrl }
            { name: 'QUEUE_BACKEND', value: 'servicebus' }
            { name: 'SERVICEBUS_FULLY_QUALIFIED_NAMESPACE', value: serviceBusFqdn }
            { name: 'DOCUMENT_STORE_BACKEND', value: 'blob' }
            { name: 'AZURE_STORAGE_ACCOUNT', value: storageAccountName }
            { name: 'AZURE_BLOB_CONTAINER', value: 'documents' }
            { name: 'MOCK_SYSTEMS_URL', value: 'http://mocks' }
            { name: 'ALWAYS_QUEUE', value: 'true' }
            { name: 'WORKER_AUTOSTART', value: 'false' }
            { name: 'FOUNDRY_PROJECT_ENDPOINT', value: foundryProjectEndpoint }
            { name: 'FOUNDRY_MODEL_NAME', value: foundryModelName }
            { name: 'CORS_ORIGINS', value: '*' }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
            { name: 'AZURE_CLIENT_ID', value: managedIdentityClientId }
            { name: 'MAIL_BRIDGE_KEY', value: 'local-mail-bridge-key' }
            { name: 'TEAMS_BRIDGE_KEY', value: 'local-teams-bridge-key' }
            { name: 'ZOHO_WEBHOOK_SECRET', value: 'local-zoho-hmac-secret' }
            { name: 'JWT_SECRET', value: 'local-dev-jwt-secret-change-in-production' }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 2
      }
    }
  }
}

resource bandb 'Microsoft.App/containerApps@2023-05-01' = {
  name: 'bandb'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppsEnvId
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [
        {
          server: acrLoginServer
          identity: managedIdentityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'bandb'
          image: bandbImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'DATABASE_URL', value: databaseUrl }
            { name: 'QUEUE_BACKEND', value: 'servicebus' }
            { name: 'SERVICEBUS_FULLY_QUALIFIED_NAMESPACE', value: serviceBusFqdn }
            { name: 'DOCUMENT_STORE_BACKEND', value: 'blob' }
            { name: 'AZURE_STORAGE_ACCOUNT', value: storageAccountName }
            { name: 'AZURE_BLOB_CONTAINER', value: 'documents' }
            { name: 'MOCK_SYSTEMS_URL', value: 'http://mocks' }
            { name: 'ALWAYS_QUEUE', value: 'true' }
            { name: 'AGENT_RUNTIME', value: 'maf' }
            { name: 'FOUNDRY_PROJECT_ENDPOINT', value: foundryProjectEndpoint }
            { name: 'FOUNDRY_MODEL_NAME', value: foundryModelName }
            { name: 'AZURE_CLIENT_ID', value: managedIdentityClientId }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 2
        rules: [
          {
            name: 'sb-invoice'
            custom: {
              type: 'azure-servicebus'
              metadata: {
                queueName: 'invoice-review'
                namespace: serviceBusFqdn
                messageCount: '1'
              }
              identity: managedIdentityId
            }
          }
          {
            name: 'sb-sales'
            custom: {
              type: 'azure-servicebus'
              metadata: {
                queueName: 'sales-lead-qualification'
                namespace: serviceBusFqdn
                messageCount: '1'
              }
              identity: managedIdentityId
            }
          }
        ]
      }
    }
  }
  dependsOn: [mocks]
}

output bandaFqdn string = banda.properties.configuration.ingress.fqdn
output mocksName string = mocks.name
output bandbName string = bandb.name
