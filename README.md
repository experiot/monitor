# Service Monitoring Tool

A comprehensive service monitoring solution that checks web content, REST API endpoints, and SSH ports, with flexible notification options including webhooks and email alerts.

## Features

- **Multi-protocol monitoring**: HTTP/HTTPS web content, REST API endpoints, and SSH port availability
- **Flexible notification system**: Webhook integrations and Gmail email alerts
- **State tracking**: Remembers service states between runs and only notifies on changes
- **Configurable checks**: Customizable timeout, content validation, and response parsing
- **Easy deployment**: Designed for cron-based scheduling

## Quick Start

### Prerequisites

- Python 3.6+
- Required packages: `requests`, `PyYAML`
- For email notifications: Gmail account with App Password enabled

### Installation

```bash
pip install requests pyyaml
```

### Configuration

1. Copy the example configuration:

```bash
cp config/monitor_config.yaml config/my_config.yaml
```

2. Edit `config/my_config.yaml` to set up your services and notification preferences

### Running the Monitor

```bash
python3 monitor.py config/my_config.yaml
```

### Scheduling with Cron

To run every 5 minutes:

```bash
*/5 * * * * /usr/bin/python3 /path/to/monitor.py /path/to/config.yaml
```

## Configuration Guide

### Basic Structure

```yaml
STATUS_DIR: "./statuses/"          # Where to store service state files
DEFAULT_TIMEOUT_MS: 5000      # Default timeout for checks in milliseconds
SILENT_MODE: false                 # Set to true to suppress console output
CLIENT_NAME: "my_server"          # Optional identifier for this monitor instance
```

### Monitoring Web Services

```yaml
urls:
  - name: "my_api_service"
    url: "https://api.example.com/health"
    checkJson: true                # Validate JSON response
    checkText: true               # Check for specific text
    okText: "Healthy"            # Text that should be present
    errorText: "Error"           # Text that should NOT be present
    okWebhook: "slack_webhook"   # Webhook to call on success
    errorWebhook: "alert_webhook" # Webhook to call on failure
    emailConfigName: "email1"     # Optional: specify email config for this service
```

**New Feature**: You can now specify `emailConfigName` in individual service configurations. When no webhook is defined, the presence of `emailConfigName` will trigger email notifications for that specific service.

### Monitoring SSH Hosts

```yaml
hosts:
  - name: "production_server"
    host: "prod.example.com"
    okWebhook: "admin_webhook"
    errorWebhook: "alert_webhook"
    emailConfigName: "email1"     # Optional: specify email config for this host
```

### Webhook Notifications

```yaml
webhooks:
  - name: "slack_webhook"
    url: "https://hooks.slack.com/services/XXX"
    method: "POST"
    headers:
      Content-Type: "application/json"
    body:
      text: "Service {service} status: {code} - {message}"
      username: "Monitor Bot"
```

### Email Notifications (SMTP - Universal)

The monitor now supports any SMTP server, including Gmail, Outlook, and custom email servers.

```yaml
email:
  smtp_server: "smtp.gmail.com"      # SMTP server address
  smtp_port: 587                     # SMTP port (587 for TLS, 465 for SSL)
  use_ssl: false                     # Use SSL instead of STARTTLS
  sender_email: "monitor@example.com" # Your email address
  password: "your_password"         # Email password or app password
  recipient_email: "admin@example.com" # Recipient email address
  subject: "ALERT: {service} status changed to {code}" # Email subject
```

#### Gmail Configuration

```yaml
email:
  smtp_server: "smtp.gmail.com"
  smtp_port: 587
  use_ssl: false
  sender_email: "your@gmail.com"
  password: "your_app_password"     # Generate in Google Account settings
  recipient_email: "admin@example.com"
  subject: "ALERT: {service} status {code}"
```

**For Gmail**: Enable 2-Factor Authentication and generate an App Password in Google Account settings.

#### Outlook/Hotmail Configuration

```yaml
email:
  smtp_server: "smtp.office365.com"
  smtp_port: 587
  use_ssl: false
  sender_email: "your@outlook.com"
  password: "your_password"
  recipient_email: "admin@example.com"
```

#### Custom SMTP Server with SSL

```yaml
email:
  smtp_server: "mail.example.com"
  smtp_port: 465
  use_ssl: true
  sender_email: "monitor@example.com"
  password: "your_password"
  recipient_email: "admin@example.com"
```

#### SMTP Configuration Options

- **smtp_server**: SMTP server address (e.g., "smtp.gmail.com", "smtp.office365.com")
- **smtp_port**: SMTP port (587 for STARTTLS, 465 for SSL)
- **use_ssl**: Set to `true` for SSL connections, `false` for STARTTLS
- **sender_email**: Your email address
- **password**: Your email password or app password
- **recipient_email**: Who should receive the alerts
- **subject**: Email subject with optional placeholders

**Note**: For security, always use App Passwords when available (Gmail, Outlook) instead of your main account password.

## Notification System

The monitor sends notifications when:
- A service changes from healthy to unhealthy (error state)
- A service recovers from unhealthy to healthy (ok state)
- The first run establishes baseline status

Notifications are sent via:
- **Webhooks**: Configured per-service for success/failure scenarios
- **Email**: Global configuration sends alerts for all state changes

### Email Configuration Priority

The monitor now supports granular email notification control through the `emailConfigName` field:

1. **Global Email Configuration**: If `email:` section exists in config, emails are sent for all services
2. **Per-Service Email Control**: Add `emailConfigName: "any_name"` to individual services
3. **Behavior**:
   - If `errorWebhook` is defined → webhook is used, email still sent (original behavior)
   - If `errorWebhook` is NOT defined but `emailConfigName` IS defined → email sent with special logging
   - If neither is defined → email sent if global email config exists (original behavior)

### Example: Mixed Notification Strategies

```yaml
urls:
  - name: "critical_service"
    url: "https://critical.example.com"
    errorWebhook: "pagerduty_webhook"  # Use webhook for critical issues
    # Email will still be sent (original behavior)
    
  - name: "important_service"
    url: "https://important.example.com"
    emailConfigName: "email1"          # Use email-only for important issues
    # No webhook, but email will be sent and logged
    
  - name: "low_priority_service"
    url: "https://low-priority.example.com"
    # No webhook or emailConfigName - email sent if global config exists
```

## Email Subject Placeholders

You can use these placeholders in email subjects:
- `{service}` - Service name from configuration
- `{code}` - HTTP status code or error code
- `{message}` - Status message
- `{client}` - Client name from configuration

## Development

### Code Structure

- `monitor.py`: Main monitoring logic
- `config/monitor_config.yaml`: Configuration template
- `statuses/`: Directory for service state files

### Key Functions

- `check_api()`: Validates HTTP/HTTPS endpoints
- `check_ssh()`: Tests SSH port availability
- `send_webhook_message()`: Sends webhook notifications
- `send_email_notification()`: Sends email alerts via Gmail
- `getCodeChanged()`: Tracks service state changes

### Adding New Check Types

To add a new protocol or check type:

1. Create a new check function following the pattern of `check_api()` or `check_ssh()`
2. Add configuration options to the YAML schema
3. Integrate the check into the main loop

### Testing

Create a test configuration with:

```yaml
SILENT_MODE: false  # See debug output
urls:
  - name: "test_service"
    url: "https://example.com"
    checkText: true
    okText: "Example"
```

## Troubleshooting

### Common Issues

**Email not sending**:
- Verify Gmail App Password is correct
- Check if "Less secure app access" needs to be enabled
- Ensure sender and recipient emails are valid

**Webhook failures**:
- Verify URL is accessible from the server
- Check firewall rules
- Validate JSON/headers format

**Permission errors**:
- Ensure STATUS_DIR is writable
- Run with appropriate user permissions

### Debugging

Enable verbose output:

```yaml
SILENT_MODE: false
```

Check status files in the STATUS_DIR for historical state information.

## Security Considerations

- Store configuration files securely (contain credentials)
- Use App Passwords instead of regular passwords for Gmail
- Set appropriate file permissions: `chmod 600 config/*.yaml`
- Consider using environment variables for sensitive data

## Contributing

Contributions welcome! Please:
- Follow existing code style
- Add tests for new features
- Update documentation
- Submit pull requests to the main branch

## Version History

### Latest Version
- **Added `emailConfigName` field**: Individual services can now specify email configuration names
- **Enhanced notification logic**: Better control over when emails are sent vs webhooks
- **Backward compatibility**: Original behavior preserved for existing configurations

### Previous Features
- Multi-protocol monitoring (HTTP, HTTPS, SSH)
- Webhook and email notifications
- State tracking and change detection
- Flexible configuration options

## License

[Specify your license here - e.g., MIT, GPL, etc.]

## Support

For issues or questions:
- Check the configuration examples
- Review the code comments
- Examine status files for clues
- Enable SILENT_MODE: false for detailed logging
