# validate-iam.ps1
# Uses IAM policy simulation against the actual Lambda execution roles.

param(
    [string]$TerraformDir = "infra/envs/dev"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Push-Location $TerraformDir
try {
    $tf = terraform output -json | ConvertFrom-Json
}
finally {
    Pop-Location
}

function Assert-Output {
    param([string[]]$Names)
    foreach ($name in $Names) {
        if (-not $tf.PSObject.Properties.Name.Contains($name)) {
            throw "Missing Terraform output: $name"
        }
        $value = $tf.PSObject.Properties[$name].Value.value
        if ($null -eq $value -or "$value" -eq "") {
            throw "Terraform output is empty: $name"
        }
        Write-Host "  ok output $name"
    }
}

Assert-Output @(
    "data_lake_bucket_arn",
    "state_machine_arn",
    "step_function_role_name",
    "raw_ingestion_queue_arn",
    "raw_dispatch_lambda_name",
    "validate_input_lambda_name",
    "process_document_lambda_name",
    "extract_ocr_lambda_name",
    "enrich_llm_lambda_name",
    "publish_metrics_lambda_name",
    "textract_policy_arn",
    "bedrock_policy_arn"
)

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

function ConvertTo-StringList {
    param([object]$Value)

    $items = New-Object System.Collections.Generic.List[string]
    foreach ($item in @($Value)) {
        if ($null -eq $item) {
            continue
        }
        if ($item -is [array]) {
            foreach ($nested in $item) {
                if ($null -ne $nested -and "$nested" -ne "") {
                    $items.Add([string]$nested)
                }
            }
        }
        elseif ("$item" -ne "") {
            $items.Add([string]$item)
        }
    }
    return $items.ToArray()
}

$bucketArn = $tf.data_lake_bucket_arn.value
$stateMachineArn = $tf.state_machine_arn.value
$queueArn = $tf.raw_ingestion_queue_arn.value
$accountId = Invoke-AwsText `
    -Arguments @("sts", "get-caller-identity", "--query", "Account", "--output", "text") `
    -Label "STS caller identity"
$region = Invoke-AwsText `
    -Arguments @("configure", "get", "region") `
    -Label "AWS configured region"
if (-not $region) {
    $region = "us-east-1"
}

function Get-OptionalOutputValue {
    param([string]$Name)
    if ($tf.PSObject.Properties.Name.Contains($Name)) {
        return $tf.PSObject.Properties[$Name].Value.value
    }
    return $null
}

function Get-LambdaRoleArn {
    param([string]$FunctionName)
    $roleArn = Invoke-AwsText `
        -Arguments @(
            "lambda",
            "get-function-configuration",
            "--function-name",
            $FunctionName,
            "--query",
            "Role",
            "--output",
            "text"
        ) `
        -Label "Lambda role lookup for $FunctionName"
    if (-not $roleArn -or $roleArn -eq "None") {
        throw "Lambda $FunctionName did not return an execution role"
    }
    return $roleArn
}

function Get-RoleNameFromArn {
    param([string]$RoleArn)
    return ($RoleArn -split "/")[-1]
}

function Assert-IamRoleExists {
    param(
        [string]$RoleName,
        [string]$Label
    )

    Invoke-AwsText `
        -Arguments @("iam", "get-role", "--role-name", $RoleName, "--query", "Role.Arn", "--output", "text") `
        -Label "IAM role lookup for $RoleName" | Out-Null
    Write-Host "  ok role $Label ($RoleName)"
}

function Assert-LambdaUsesRole {
    param(
        [string]$FunctionName,
        [string]$ExpectedRoleName,
        [string]$Label
    )

    $roleArn = Get-LambdaRoleArn $FunctionName
    $actualRoleName = Get-RoleNameFromArn $roleArn
    if ($actualRoleName -ne $ExpectedRoleName) {
        throw "Lambda $FunctionName uses role $actualRoleName, expected $ExpectedRoleName"
    }
    Assert-IamRoleExists -RoleName $actualRoleName -Label $Label
    return $roleArn
}

function Assert-InlinePolicies {
    param(
        [string]$RoleName,
        [string[]]$PolicyNames,
        [string]$Label
    )

    $existing = ConvertTo-StringList (
        Invoke-AwsJson `
            -Arguments @("iam", "list-role-policies", "--role-name", $RoleName, "--query", "PolicyNames", "--output", "json") `
            -Label "inline policy lookup for $RoleName"
    )
    $missing = @($PolicyNames | Where-Object { $existing -notcontains $_ })
    if ($missing.Count -gt 0) {
        throw "Missing inline IAM policies for $Label ($RoleName): $($missing -join ', ')"
    }
    Write-Host "  ok inline policies ${Label}: $($PolicyNames -join ', ')"
}

function Assert-ManagedPolicies {
    param(
        [string]$RoleName,
        [string[]]$PolicyArns,
        [string]$Label
    )

    $existing = ConvertTo-StringList (
        Invoke-AwsJson `
            -Arguments @("iam", "list-attached-role-policies", "--role-name", $RoleName, "--query", "AttachedPolicies[].PolicyArn", "--output", "json") `
            -Label "managed policy lookup for $RoleName"
    )
    $missing = @($PolicyArns | Where-Object { $existing -notcontains $_ })
    if ($missing.Count -gt 0) {
        throw "Missing managed IAM policies for $Label ($RoleName): $($missing -join ', ')"
    }
    Write-Host "  ok managed policies $Label"
}

function Get-LambdaEnvValue {
    param(
        [string]$FunctionName,
        [string]$Name
    )
    $config = Invoke-AwsJson `
        -Arguments @("lambda", "get-function-configuration", "--function-name", $FunctionName, "--output", "json") `
        -Label "Lambda environment lookup for $FunctionName"
    $variables = $config.Environment.Variables
    if ($variables -and $variables.PSObject.Properties.Name.Contains($Name)) {
        return $variables.PSObject.Properties[$Name].Value
    }
    return $null
}

function Get-BedrockResources {
    param([string]$FunctionName)
    $modelId = Get-LambdaEnvValue -FunctionName $FunctionName -Name "BEDROCK_MODEL_ID"
    if (-not $modelId) {
        return @()
    }
    return @(
        "arn:aws:bedrock:${region}::foundation-model/$modelId",
        "arn:aws:bedrock:${region}:${accountId}:inference-profile/$modelId",
        "arn:aws:bedrock:*::foundation-model/*"
    )
}

function Assert-Allowed {
    param(
        [string]$RoleArn,
        [string[]]$Actions,
        [string[]]$Resources,
        [string]$Label,
        [string[]]$ContextEntries = @()
    )

    $args = @(
        "iam",
        "simulate-principal-policy",
        "--policy-source-arn",
        $RoleArn,
        "--action-names"
    ) + $Actions + @(
        "--resource-arns"
    ) + $Resources

    if ($ContextEntries.Count -gt 0) {
        $args += @("--context-entries")
        $args += $ContextEntries
    }

    $simulation = Invoke-AwsJson `
        -Arguments ($args + @("--output", "json")) `
        -Label "IAM simulation for $Label"

    $denied = @($simulation.EvaluationResults | Where-Object {
        $_.EvalDecision -ne "allowed"
    })

    if ($denied.Count -gt 0) {
        $summary = $denied | ForEach-Object {
            "$($_.EvalActionName) on $($_.EvalResourceName) => $($_.EvalDecision)"
        }
        throw "IAM validation failed for $Label ($RoleArn): $($summary -join '; ')"
    }

    Write-Host "  ok $Label"
}

$rawDispatchName = $tf.raw_dispatch_lambda_name.value
$validateInputName = $tf.validate_input_lambda_name.value
$processDocumentName = $tf.process_document_lambda_name.value
$publishMetricsName = $tf.publish_metrics_lambda_name.value
$extractOcrName = Get-OptionalOutputValue "extract_ocr_lambda_name"
$enrichLlmName = Get-OptionalOutputValue "enrich_llm_lambda_name"
$stateMachineName = $tf.state_machine_name.value
$stepFunctionRoleName = $tf.step_function_role_name.value
$textractPolicyArn = $tf.textract_policy_arn.value
$bedrockPolicyArn = $tf.bedrock_policy_arn.value

$rawDispatchRoleName = "$rawDispatchName-role"
$validateInputRoleName = "$validateInputName-role"
$processDocumentRoleName = "$processDocumentName-role"
$publishMetricsRoleName = "$publishMetricsName-role"

$rawDispatchRole = Assert-LambdaUsesRole `
    -FunctionName $rawDispatchName `
    -ExpectedRoleName $rawDispatchRoleName `
    -Label "raw_dispatch"
$validateInputRole = Assert-LambdaUsesRole `
    -FunctionName $validateInputName `
    -ExpectedRoleName $validateInputRoleName `
    -Label "validate_input"
$processDocumentRole = Assert-LambdaUsesRole `
    -FunctionName $processDocumentName `
    -ExpectedRoleName $processDocumentRoleName `
    -Label "process_document"
$publishMetricsRole = Assert-LambdaUsesRole `
    -FunctionName $publishMetricsName `
    -ExpectedRoleName $publishMetricsRoleName `
    -Label "publish_metrics"

Assert-IamRoleExists -RoleName $stepFunctionRoleName -Label "step_functions"

Assert-InlinePolicies `
    -RoleName $rawDispatchRoleName `
    -PolicyNames @("logging", "start_execution", "sqs_consume") `
    -Label "raw_dispatch"
Assert-InlinePolicies `
    -RoleName $validateInputRoleName `
    -PolicyNames @("logging") `
    -Label "validate_input"
Assert-InlinePolicies `
    -RoleName $processDocumentRoleName `
    -PolicyNames @("logging", "data_lake_access") `
    -Label "process_document"
Assert-InlinePolicies `
    -RoleName $publishMetricsRoleName `
    -PolicyNames @("logging", "cloudwatch_write") `
    -Label "publish_metrics"
Assert-InlinePolicies `
    -RoleName $stepFunctionRoleName `
    -PolicyNames @("${stateMachineName}-logging", "lambda_invoke") `
    -Label "step_functions"

Assert-ManagedPolicies `
    -RoleName $processDocumentRoleName `
    -PolicyArns @($textractPolicyArn, $bedrockPolicyArn) `
    -Label "process_document"

Assert-Allowed `
    -RoleArn $rawDispatchRole `
    -Actions @("states:StartExecution") `
    -Resources @($stateMachineArn) `
    -Label "raw_dispatch StartExecution"

Assert-Allowed `
    -RoleArn $rawDispatchRole `
    -Actions @(
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes",
        "sqs:ChangeMessageVisibility"
    ) `
    -Resources @($queueArn) `
    -Label "raw_dispatch SQS consume"

Assert-Allowed `
    -RoleArn $processDocumentRole `
    -Actions @("s3:GetObject") `
    -Resources @(
        "$bucketArn/raw/*",
        "$bucketArn/silver/valid/*"
    ) `
    -Label "process_document S3 reads"

Assert-Allowed `
    -RoleArn $processDocumentRole `
    -Actions @("s3:ListBucket") `
    -Resources @($bucketArn) `
    -ContextEntries @("ContextKeyName=s3:prefix,ContextKeyValues=silver/valid/run_id=runtime-precheck/precheck.json,ContextKeyType=string") `
    -Label "process_document silver idempotency list"

Assert-Allowed `
    -RoleArn $processDocumentRole `
    -Actions @("s3:PutObject") `
    -Resources @(
        "$bucketArn/bronze/textract-json/*",
        "$bucketArn/silver/valid/*",
        "$bucketArn/silver/rejected/*",
        "$bucketArn/errors/*"
    ) `
    -Label "process_document S3 writes"

Assert-Allowed `
    -RoleArn $processDocumentRole `
    -Actions @("textract:AnalyzeExpense") `
    -Resources @("*") `
    -Label "process_document Textract"

$processBedrockResources = Get-BedrockResources -FunctionName $processDocumentName
if ($processBedrockResources.Count -gt 0) {
    Assert-Allowed `
        -RoleArn $processDocumentRole `
        -Actions @("bedrock:InvokeModel") `
        -Resources $processBedrockResources `
        -Label "process_document Bedrock"
}

if ($extractOcrName) {
    $extractOcrRoleName = "$extractOcrName-role"
    $extractOcrRole = Assert-LambdaUsesRole `
        -FunctionName $extractOcrName `
        -ExpectedRoleName $extractOcrRoleName `
        -Label "extract_ocr"
    Assert-InlinePolicies `
        -RoleName $extractOcrRoleName `
        -PolicyNames @("logging", "data_lake_access") `
        -Label "extract_ocr"
    Assert-ManagedPolicies `
        -RoleName $extractOcrRoleName `
        -PolicyArns @($textractPolicyArn) `
        -Label "extract_ocr"

    Assert-Allowed `
        -RoleArn $extractOcrRole `
        -Actions @("s3:GetObject") `
        -Resources @(
            "$bucketArn/raw/*",
            "$bucketArn/silver/valid/*"
        ) `
        -Label "extract_ocr S3 reads"

    Assert-Allowed `
        -RoleArn $extractOcrRole `
        -Actions @("s3:ListBucket") `
        -Resources @($bucketArn) `
        -ContextEntries @("ContextKeyName=s3:prefix,ContextKeyValues=silver/valid/run_id=runtime-precheck/precheck.json,ContextKeyType=string") `
        -Label "extract_ocr silver idempotency list"

    Assert-Allowed `
        -RoleArn $extractOcrRole `
        -Actions @("s3:PutObject") `
        -Resources @("$bucketArn/bronze/textract-json/*") `
        -Label "extract_ocr bronze write"

    Assert-Allowed `
        -RoleArn $extractOcrRole `
        -Actions @("textract:AnalyzeExpense") `
        -Resources @("*") `
        -Label "extract_ocr Textract"
}

if ($enrichLlmName) {
    $enrichLlmRoleName = "$enrichLlmName-role"
    $enrichLlmRole = Assert-LambdaUsesRole `
        -FunctionName $enrichLlmName `
        -ExpectedRoleName $enrichLlmRoleName `
        -Label "enrich_llm"
    Assert-InlinePolicies `
        -RoleName $enrichLlmRoleName `
        -PolicyNames @("logging", "data_lake_access") `
        -Label "enrich_llm"
    Assert-ManagedPolicies `
        -RoleName $enrichLlmRoleName `
        -PolicyArns @($bedrockPolicyArn) `
        -Label "enrich_llm"

    Assert-Allowed `
        -RoleArn $enrichLlmRole `
        -Actions @("s3:GetObject") `
        -Resources @("$bucketArn/bronze/textract-json/*") `
        -Label "enrich_llm bronze read"

    Assert-Allowed `
        -RoleArn $enrichLlmRole `
        -Actions @("s3:PutObject") `
        -Resources @(
            "$bucketArn/silver/valid/*",
            "$bucketArn/silver/rejected/*",
            "$bucketArn/errors/*"
        ) `
        -Label "enrich_llm final writes"

    $enrichBedrockResources = Get-BedrockResources -FunctionName $enrichLlmName
    if ($enrichBedrockResources.Count -gt 0) {
        Assert-Allowed `
            -RoleArn $enrichLlmRole `
            -Actions @("bedrock:InvokeModel") `
            -Resources $enrichBedrockResources `
            -Label "enrich_llm Bedrock"
    }
}

$lambdaArns = @(
    $tf.validate_input_lambda_name.value,
    $tf.process_document_lambda_name.value,
    $extractOcrName,
    $enrichLlmName,
    $tf.publish_metrics_lambda_name.value
) | Where-Object { $_ }

$lambdaInvokeResources = @()
foreach ($nameOrArn in $lambdaArns) {
    if ($nameOrArn -like "arn:aws:lambda:*") {
        $lambdaInvokeResources += $nameOrArn
        $lambdaInvokeResources += "$nameOrArn`:*"
    }
    else {
        $arn = Invoke-AwsText `
            -Arguments @(
                "lambda",
                "get-function-configuration",
                "--function-name",
                $nameOrArn,
                "--query",
                "FunctionArn",
                "--output",
                "text"
            ) `
            -Label "Lambda ARN lookup for $nameOrArn"
        $lambdaInvokeResources += $arn
        $lambdaInvokeResources += "$arn`:*"
    }
}

Assert-Allowed `
    -RoleArn "arn:aws:iam::${accountId}:role/$stepFunctionRoleName" `
    -Actions @("lambda:InvokeFunction") `
    -Resources $lambdaInvokeResources `
    -Label "step_functions Lambda invoke"

Assert-Allowed `
    -RoleArn $publishMetricsRole `
    -Actions @("cloudwatch:PutMetricData") `
    -Resources @("*") `
    -Label "publish_metrics CloudWatch"
