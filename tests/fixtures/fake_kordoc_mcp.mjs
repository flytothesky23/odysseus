import readline from 'node:readline';

const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });

function send(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

input.on('line', (line) => {
  const request = JSON.parse(line);
  if (request.method === 'initialize') {
    send({
      jsonrpc: '2.0',
      id: request.id,
      result: {
        protocolVersion: request.params.protocolVersion,
        capabilities: { tools: {} },
        serverInfo: { name: 'fake-kordoc', version: '4.2.5-test' },
      },
    });
    return;
  }
  if (request.method === 'tools/list') {
    send({
      jsonrpc: '2.0',
      id: request.id,
      result: {
        tools: [{ name: 'parse_document', inputSchema: { type: 'object' } }],
      },
    });
    return;
  }
  if (request.method === 'tools/call') {
    send({
      jsonrpc: '2.0',
      id: request.id,
      result: { content: [{ type: 'text', text: 'fixture parsed' }] },
    });
  }
});
