# Contributing to Gattino

Thank you for your interest in contributing to Gattino!

## How to Contribute

1. Fork the repository
2. Create a new branch for your feature (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run the tests (`python -m unittest discover tests`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/gattino.git

# Add symlink to the repository in your kitty config
ln -s ~/path/to/gattino ~/.config/kitty/gattino 

# Run tests
python -m unittest discover tests
```

## Code Style

- Follow PEP 8 guidelines
- Keep functions focused and single-purpose

## Testing

- Add tests for new features
- Ensure all tests pass before submitting a PR
- Update existing tests when modifying features
