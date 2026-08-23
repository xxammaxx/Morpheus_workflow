# Provider failover live proof

Offline provider-failover behavior remains bounded and separate from semantic
task retry. Bidirectional live failover requires two independently promoted
providers; it was not run because the pool has zero promoted live providers.
