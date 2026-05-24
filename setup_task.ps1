$scriptDir = "E:\projects\us-market-summary"
$taskName  = "US Market Summary"

$action = New-ScheduledTaskAction `
    -Execute  "cmd.exe" `
    -Argument "/c `"$scriptDir\run.bat`""

$trigger = New-ScheduledTaskTrigger -Daily -At "07:00"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName   $taskName `
    -Action     $action `
    -Trigger    $trigger `
    -Settings   $settings `
    -Description "US market summary to Discord" `
    -RunLevel   Highest `
    -Force

Write-Host "Done: $taskName registered at 07:00 daily"
