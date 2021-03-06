/*
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package org.apache.beam.sdk.coders;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.Serializable;
import java.util.Collections;
import java.util.List;

/**
 * An abstract base class for writing a {@link Coder} class that encodes itself via Java
 * serialization.
 *
 * <p>To complete an implementation, subclasses must implement {@link Coder#encode}
 * and {@link Coder#decode} methods.
 *
 * <p>Not to be confused with {@link SerializableCoder} that encodes objects that implement the
 * {@link Serializable} interface.
 *
 * @param <T> the type of elements handled by this coder
 */
public abstract class CustomCoder<T> extends Coder<T>
    implements Serializable {

  @Override
  public void encode(T value, OutputStream outStream)
      throws CoderException, IOException {
    encode(value, outStream, Coder.Context.NESTED);
  }

  @Deprecated
  @Override
  public void encodeOuter(T value, OutputStream outStream)
      throws CoderException, IOException {
    encode(value, outStream, Coder.Context.OUTER);
  }

  @Deprecated
  public void encode(T value, OutputStream outStream, Coder.Context context)
      throws CoderException, IOException {
    if (context == Coder.Context.NESTED) {
      encode(value, outStream);
    } else {
      encodeOuter(value, outStream);
    }
  }

  @Override
  public T decode(InputStream inStream) throws CoderException, IOException {
    return decode(inStream, Coder.Context.NESTED);
  }

  @Deprecated
  @Override
  public T decodeOuter(InputStream inStream) throws CoderException, IOException {
    return decode(inStream, Coder.Context.OUTER);
  }

  @Deprecated
  public T decode(InputStream inStream, Coder.Context context)
      throws CoderException, IOException {
    if (context == Coder.Context.NESTED) {
      return decode(inStream);
    } else {
      return decodeOuter(inStream);
    }
  }

  /**
   * {@inheritDoc}.
   *
   * <p>Returns an empty list. A {@link CustomCoder} has no default argument {@link Coder coders}.
   */
  @Override
  public List<? extends Coder<?>> getCoderArguments() {
    return Collections.emptyList();
  }

  /**
   * {@inheritDoc}
   *
   * @throws NonDeterministicException a {@link CustomCoder} is presumed
   * nondeterministic.
   */
  @Override
  public void verifyDeterministic() throws NonDeterministicException {
    throw new NonDeterministicException(this,
        "CustomCoder implementations must override verifyDeterministic,"
        + " or they are presumed nondeterministic.");
  }

  // This coder inherits isRegisterByteSizeObserverCheap,
  // getEncodedElementByteSize and registerByteSizeObserver
  // from StructuredCoder. Override if we can do better.
}
