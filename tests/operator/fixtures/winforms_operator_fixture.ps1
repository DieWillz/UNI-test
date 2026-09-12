param(
  [Parameter(Mandatory=$true)][string]$OutputPath,
  [Parameter(Mandatory=$true)][string]$Title
)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$form = New-Object System.Windows.Forms.Form
$form.Text = $Title
$form.Width = 560; $form.Height = 430
$form.StartPosition = 'CenterScreen'
$box = New-Object System.Windows.Forms.TextBox
$box.AccessibleName = 'Document'
$box.Left = 30; $box.Top = 30; $box.Width = 470; $box.Height = 75
$box.Multiline = $true
$check = New-Object System.Windows.Forms.CheckBox
$check.Text = 'Remember me'; $check.AccessibleName = 'Remember me'
$check.Left = 30; $check.Top = 120; $check.Width = 130
$combo = New-Object System.Windows.Forms.ComboBox
$combo.AccessibleName = 'Theme'
$combo.Left = 180; $combo.Top = 116; $combo.Width = 140
[void]$combo.Items.Add('Dark'); [void]$combo.Items.Add('Light')
$combo.SelectedIndex = 0
$button = New-Object System.Windows.Forms.Button
$button.Text = 'Save'; $button.AccessibleName = 'Save'
$button.Left = 30; $button.Top = 170; $button.Width = 100
$status = New-Object System.Windows.Forms.Label
$status.Text = 'Idle'; $status.AccessibleName = 'Status'
$status.Left = 150; $status.Top = 177; $status.Width = 280
$notes = New-Object System.Windows.Forms.RichTextBox
$notes.AccessibleName = 'Notes'
$notes.Text = 'Document seed'
$notes.Left = 30; $notes.Top = 220; $notes.Width = 470; $notes.Height = 110
$button.Add_Click({
  [System.IO.File]::WriteAllText($OutputPath, $box.Text, [System.Text.UTF8Encoding]::new($false))
  $status.Text = 'Saved'
})
$form.Controls.AddRange(@($box,$check,$combo,$button,$status,$notes))
[System.Windows.Forms.Application]::Run($form)
