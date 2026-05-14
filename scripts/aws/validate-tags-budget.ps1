# validate-tags-budget.ps1
# Validates mandatory resource tags and the project budget cost filter.

param(
    [string]$TerraformDir = "infra/envs/dev",
    [string]$AwsRegion = "us-east-1",
    [string]$ProjectName = "invoice-pipeline",
    [string]$Environment = "dev",
    [string[]]$RequiredTagKeys = @("Project", "Environment", "ManagedBy", "Owner", "Platform")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
if (-not $env:AWS_DEFAULT_REGION) {
    $env:AWS_DEFAULT_REGION = $AwsRegion
}

function Invoke-AwsText {
    param(
        [string[]]$Arguments,
        [string]$Label
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & aws @Arguments 2>&1
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($LASTEXITCODE -ne 0) {
        throw "AWS CLI failed for ${Label}: $($output -join [Environment]::NewLine)"
    }
    return ($output -join "`n").Trim()
}

function Invoke-AwsJson {
    param(
        [string[]]$Arguments,
        [string]$Label
    )

    $text = Invoke-AwsText -Arguments $Arguments -Label $Label
    if (-not $text) {
        throw "AWS CLI returned empty JSON for $Label"
    }
    return $text | ConvertFrom-Json
}

function Convert-TagArrayToMap {
    param([object]$Tags)

    $map = @{}
    if ($null -eq $Tags) {
        return $map
    }
    if ($Tags -is [hashtable]) {
        foreach ($key in $Tags.Keys) {
            $map[[string]$key] = [string]$Tags[$key]
        }
        return $map
    }
    if ($Tags -is [System.Management.Automation.PSCustomObject]) {
        foreach ($property in $Tags.PSObject.Properties) {
            $map[[string]$property.Name] = [string]$property.Value
        }
        return $map
    }

    foreach ($tag in @($Tags)) {
        if ($null -eq $tag) {
            continue
        }
        if ($tag.PSObject.Properties.Name -contains "Key") {
            $map[[string]$tag.Key] = [string]$tag.Value
        }
        elseif ($tag.PSObject.Properties.Name -contains "key") {
            $map[[string]$tag.key] = [string]$tag.value
        }
    }
    return $map
}

function Assert-RequiredTags {
    param(
        [hashtable]$Tags,
        [string]$Label
    )

    $missing = @($RequiredTagKeys | Where-Object { -not $Tags.ContainsKey($_) -or -not $Tags[$_] })
    if ($missing.Count -gt 0) {
        throw "Missing required tags for ${Label}: $($missing -join ', ')"
    }
    if ($Tags["Project"] -ne $ProjectName) {
        throw "Tag Project mismatch for ${Label}: expected '$ProjectName', found '$($Tags["Project"])'"
    }
    if ($Tags["Environment"] -ne $Environment) {
        throw "Tag Environment mismatch for ${Label}: expected '$Environment', found '$($Tags["Environment"])'"
    }
    Write-Host "  ok tags $Label"
}

function Get-S3BucketTags {
    param([string]$BucketName)
    $result = Invoke-AwsJson `
        -Arguments @("s3api", "get-bucket-tagging", "--bucket", $BucketName, "--output", "json") `
        -Label "S3 tags for $BucketName"
    return Convert-TagArrayToMap $result.TagSet
}

function Get-LambdaTags {
    param([string]$FunctionName)
    $arn = Invoke-AwsText `
        -Arguments @("lambda", "get-function-configuration", "--function-name", $FunctionName, "--query", "FunctionArn", "--output", "text") `
        -Label "Lambda ARN for $FunctionName"
    $result = Invoke-AwsJson `
        -Arguments @("lambda", "list-tags", "--resource", $arn, "--output", "json") `
        -Label "Lambda tags for $FunctionName"
    return Convert-TagArrayToMap $result.Tags
}

function Get-SqsTags {
    param([string]$QueueUrl)
    $result = Invoke-AwsJson `
        -Arguments @("sqs", "list-queue-tags", "--queue-url", $QueueUrl, "--output", "json") `
        -Label "SQS tags for $QueueUrl"
    return Convert-TagArrayToMap $result.Tags
}

function Get-StateMachineTags {
    param([string]$StateMachineArn)
    $result = Invoke-AwsJson `
        -Arguments @("stepfunctions", "list-tags-for-resource", "--resource-arn", $StateMachineArn, "--output", "json") `
        -Label "Step Functions tags for $StateMachineArn"
    return Convert-TagArrayToMap $result.tags
}

function Get-IamRoleTags {
    param([string]$RoleName)
    $result = Invoke-AwsJson `
        -Arguments @("iam", "list-role-tags", "--role-name", $RoleName, "--output", "json") `
        -Label "IAM role tags for $RoleName"
    return Convert-TagArrayToMap $result.Tags
}

function Get-IamPolicyTags {
    param([string]$PolicyArn)
    $result = Invoke-AwsJson `
        -Arguments @("iam", "list-policy-tags", "--policy-arn", $PolicyArn, "--output", "json") `
        -Label "IAM policy tags for $PolicyArn"
    return Convert-TagArrayToMap $result.Tags
}

function Get-LogGroupTags {
    param([string]$LogGroupName)
    $logGroup = Invoke-AwsJson `
        -Arguments @("logs", "describe-log-groups", "--log-group-name-prefix", $LogGroupName, "--query", "logGroups[?logGroupName=='$LogGroupName'] | [0]", "--output", "json") `
        -Label "CloudWatch log group lookup for $LogGroupName"
    if ($null -eq $logGroup) {
        throw "CloudWatch log group not found: $LogGroupName"
    }
    $arn = [string]$logGroup.arn
    $arn = $arn.TrimEnd(":*")
    $result = Invoke-AwsJson `
        -Arguments @("logs", "list-tags-for-resource", "--resource-arn", $arn, "--output", "json") `
        -Label "CloudWatch log group tags for $LogGroupName"
    return Convert-TagArrayToMap $result.tags
}

function Assert-BudgetAssociation {
    param(
        [string]$AccountId,
        [string]$BudgetName
    )

    $budget = Invoke-AwsJson `
        -Arguments @("budgets", "describe-budget", "--account-id", $AccountId, "--budget-name", $BudgetName, "--output", "json") `
        -Label "Budget lookup for $BudgetName"
    $filters = @($budget.Budget.CostFilters.TagKeyValue)
    $expected = "Project`$$ProjectName"
    if ($filters -notcontains $expected) {
        throw "Budget $BudgetName is not associated with Project tag filter '$expected'"
    }
    Write-Host "  ok budget filter $BudgetName -> $expected"
}

Push-Location $TerraformDir
try {
    $tf = terraform output -json | ConvertFrom-Json
}
finally {
    Pop-Location
}

$accountId = Invoke-AwsText `
    -Arguments @("sts", "get-caller-identity", "--query", "Account", "--output", "text") `
    -Label "STS caller identity"

Assert-BudgetAssociation -AccountId $accountId -BudgetName $tf.budget_name.value

Assert-RequiredTags -Tags (Get-S3BucketTags $tf.artifact_bucket_name.value) -Label "artifact bucket"
Assert-RequiredTags -Tags (Get-S3BucketTags $tf.data_lake_bucket_name.value) -Label "data lake bucket"

$lambdaOutputs = @(
    "raw_dispatch_lambda_name",
    "validate_input_lambda_name",
    "process_document_lambda_name",
    "extract_ocr_lambda_name",
    "enrich_llm_lambda_name",
    "publish_metrics_lambda_name"
)

foreach ($outputName in $lambdaOutputs) {
    if ($tf.PSObject.Properties.Name.Contains($outputName)) {
        $functionName = $tf.PSObject.Properties[$outputName].Value.value
        Assert-RequiredTags -Tags (Get-LambdaTags $functionName) -Label "lambda $functionName"
        Assert-RequiredTags -Tags (Get-LogGroupTags "/aws/lambda/$functionName") -Label "log group /aws/lambda/$functionName"
        Assert-RequiredTags -Tags (Get-IamRoleTags "$functionName-role") -Label "role $functionName-role"
    }
}

Assert-RequiredTags -Tags (Get-SqsTags $tf.raw_ingestion_queue_url.value) -Label "raw ingestion queue"
Assert-RequiredTags -Tags (Get-SqsTags $tf.raw_ingestion_dlq_url.value) -Label "raw ingestion DLQ"
Assert-RequiredTags -Tags (Get-StateMachineTags $tf.state_machine_arn.value) -Label "state machine"
Assert-RequiredTags -Tags (Get-IamRoleTags $tf.step_function_role_name.value) -Label "step function role"
Assert-RequiredTags -Tags (Get-IamPolicyTags $tf.textract_policy_arn.value) -Label "textract managed policy"
Assert-RequiredTags -Tags (Get-IamPolicyTags $tf.bedrock_policy_arn.value) -Label "bedrock managed policy"

$stateMachineLogGroup = "/aws/vendedlogs/states/$($tf.state_machine_name.value)"
Assert-RequiredTags -Tags (Get-LogGroupTags $stateMachineLogGroup) -Label "log group $stateMachineLogGroup"

Write-Host "`n[tag-budget] OK" -ForegroundColor Green
